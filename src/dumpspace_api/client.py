from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from enum import IntFlag
from threading import Lock
from typing import Callable, Dict, Iterable, Optional, Union
from urllib.request import urlopen


class ContentTypes(IntFlag):
    CLASSES = 1 << 1
    STRUCTS = 1 << 2
    ENUMS = 1 << 3
    FUNCTIONS = 1 << 4
    OFFSETS = 1 << 5
    ALL = CLASSES | STRUCTS | ENUMS | FUNCTIONS | OFFSETS


@dataclass(frozen=True)
class OffsetInfo:
    offset: int = 0
    size: int = 0
    is_bit: bool = False
    bit_offset: int = 0
    valid: bool = False

    def __bool__(self) -> bool:
        return self.valid


class DSAPI:
    website = "https://raw.githubusercontent.com/Spuckwaffel/dumpspace/refs/heads/main/Games/"
    game_list = "https://raw.githubusercontent.com/Spuckwaffel/dumpspace/refs/heads/main/Games/GameList.json"

    _game_list_lock = Lock()
    _game_list_cache: Optional[dict] = None

    def __init__(self, game_hash: str, fetcher: Optional[Callable[[str], bytes]] = None) -> None:
        self.game_id = game_hash
        self.engine = ""
        self.location = ""
        self._fetcher = fetcher or self._default_fetcher

        self.class_member_map: Dict[str, OffsetInfo] = {}
        self.class_size_map: Dict[str, int] = {}
        self.function_offset_map: Dict[str, int] = {}
        self.enum_name_map: Dict[str, str] = {}
        self.offset_map: Dict[str, int] = {}

    @staticmethod
    def _default_fetcher(url: str) -> bytes:
        with urlopen(url, timeout=30) as response:
            return response.read()

    @classmethod
    def _download_game_list(cls, fetcher: Callable[[str], bytes]) -> dict:
        with cls._game_list_lock:
            if cls._game_list_cache is None:
                raw = fetcher(cls.game_list).decode("utf-8")
                cls._game_list_cache = json.loads(raw)
            return cls._game_list_cache

    def _download_gzip_json(self, url: str) -> dict:
        compressed = self._fetcher(url)
        data = gzip.decompress(compressed).decode("utf-8")
        return json.loads(data)

    def _populate_class_like_data(self, items: Iterable[dict], file_version: int) -> None:
        for class_entry in items:
            for class_name, member_entries in class_entry.items():
                for member_entry in member_entries:
                    for member_name, value in member_entry.items():
                        if member_name == "__MDKClassSize":
                            self.class_size_map[class_name] = int(value)
                            continue
                        if member_name == "__InheritInfo":
                            continue

                        values = list(value)
                        is_bit = (len(values) == 4) if file_version == 10201 else (len(values) == 5)
                        bit_offset = int(values[3]) if (is_bit and file_version == 10201) else int(values[4]) if is_bit else 0

                        key_member_name = member_name[:-4] if (is_bit and file_version == 10201 and member_name.endswith("_Bit")) else member_name

                        self.class_member_map[f"{class_name}{key_member_name}"] = OffsetInfo(
                            offset=int(values[1]),
                            size=int(values[2]),
                            is_bit=is_bit,
                            bit_offset=bit_offset,
                            valid=True,
                        )

    def download_content(self, types: ContentTypes = ContentTypes.ALL) -> None:
        game_list_json = self._download_game_list(self._fetcher)
        for game in game_list_json.get("games", []):
            if game.get("hash", "") == self.game_id:
                self.engine = game.get("engine", "")
                self.location = game.get("location", "")
                break
        if not self.engine or not self.location:
            raise ValueError("engine or location of the target game ID could not be found")

        base_url = f"{self.website}{self.engine}/{self.location}"

        if types & ContentTypes.CLASSES:
            class_json = self._download_gzip_json(f"{base_url}/ClassesInfo.json.gz")
            self._populate_class_like_data(class_json.get("data", []), int(class_json.get("version", 0)))

        if types & ContentTypes.STRUCTS:
            struct_json = self._download_gzip_json(f"{base_url}/StructsInfo.json.gz")
            self._populate_class_like_data(struct_json.get("data", []), int(struct_json.get("version", 0)))

        if types & ContentTypes.ENUMS:
            enum_json = self._download_gzip_json(f"{base_url}/EnumsInfo.json.gz")
            for enum_entry in enum_json.get("data", []):
                for enum_name, enum_values in enum_entry.items():
                    for value_entry in enum_values[0]:
                        for entry_name, entry_value in value_entry.items():
                            self.enum_name_map[f"{enum_name}{int(entry_value)}"] = entry_name

        if types & ContentTypes.FUNCTIONS:
            function_json = self._download_gzip_json(f"{base_url}/FunctionsInfo.json.gz")
            for function_entry in function_json.get("data", []):
                for function_class, functions in function_entry.items():
                    for function_data in functions:
                        for function_name, function_values in function_data.items():
                            self.function_offset_map[f"{function_class}{function_name}"] = int(function_values[2])

        if types & ContentTypes.OFFSETS:
            offset_json = self._download_gzip_json(f"{base_url}/OffsetsInfo.json.gz")
            for offset_entry in offset_json.get("data", []):
                self.offset_map[str(offset_entry[0])] = int(offset_entry[1])

    def get_offset(self, class_name: str, member_name: Optional[str] = None) -> Union[int, OffsetInfo]:
        if member_name is None:
            return self.offset_map.get(class_name, 0)
        return self.class_member_map.get(f"{class_name}{member_name}", OffsetInfo())

    def get_sizeof_class(self, class_name: str) -> int:
        return self.class_size_map.get(class_name, 0)

    def get_function_offset(self, function_class: str, function_name: str) -> int:
        return self.function_offset_map.get(f"{function_class}{function_name}", 0)

    def get_enum_name(self, enum_class: str, value: int) -> str:
        return self.enum_name_map.get(f"{enum_class}{value}", "")
