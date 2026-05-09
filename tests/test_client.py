import gzip
import json
import unittest

from dumpspace_api import ContentTypes, DSAPI


def _gzip_json(payload: dict) -> bytes:
    return gzip.compress(json.dumps(payload).encode("utf-8"))


class DSAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = "https://raw.githubusercontent.com/Spuckwaffel/dumpspace/refs/heads/main/Games/UE5/TestGame"
        self.urls = {
            DSAPI.game_list: json.dumps(
                {
                    "games": [
                        {"hash": "abc123", "engine": "UE5", "location": "TestGame"},
                    ]
                }
            ).encode("utf-8"),
            f"{self.base}/ClassesInfo.json.gz": _gzip_json(
                {
                    "version": 10201,
                    "data": [
                        {
                            "UWorld": [
                                {"__MDKClassSize": 64},
                                {"OwningGameInstance": [0, 16, 8]},
                                {"bReplicated_Bit": [0, 32, 1, 3]},
                            ]
                        }
                    ],
                }
            ),
            f"{self.base}/StructsInfo.json.gz": _gzip_json({"version": 10201, "data": []}),
            f"{self.base}/EnumsInfo.json.gz": _gzip_json(
                {
                    "version": 10201,
                    "data": [
                        {
                            "EFortRarity": [
                                [
                                    {"EFortRarity__Common": 0},
                                    {"EFortRarity__Legendary": 4},
                                ]
                            ]
                        }
                    ],
                }
            ),
            f"{self.base}/FunctionsInfo.json.gz": _gzip_json(
                {
                    "version": 10201,
                    "data": [
                        {
                            "AFortWeapon": [
                                {"WeaponDataIsValid": [0, 0, 0x1234]},
                            ]
                        }
                    ],
                }
            ),
            f"{self.base}/OffsetsInfo.json.gz": _gzip_json(
                {
                    "version": 10201,
                    "data": [["OFFSET_UWORLD", 0x777]],
                }
            ),
        }

    def test_download_content_and_lookups(self) -> None:
        def fetcher(url: str) -> bytes:
            return self.urls[url]

        DSAPI._game_list_cache = None
        api = DSAPI("abc123", fetcher=fetcher)
        api.download_content()

        self.assertEqual(api.get_offset("OFFSET_UWORLD"), 0x777)
        self.assertEqual(api.get_sizeof_class("UWorld"), 64)
        self.assertEqual(api.get_function_offset("AFortWeapon", "WeaponDataIsValid"), 0x1234)
        self.assertEqual(api.get_enum_name("EFortRarity", 4), "EFortRarity__Legendary")

        offset = api.get_offset("UWorld", "OwningGameInstance")
        self.assertTrue(offset)
        self.assertEqual(offset.offset, 16)
        self.assertEqual(offset.size, 8)
        self.assertFalse(offset.is_bit)

        bit_offset = api.get_offset("UWorld", "bReplicated")
        self.assertTrue(bit_offset)
        self.assertTrue(bit_offset.is_bit)
        self.assertEqual(bit_offset.bit_offset, 3)

    def test_missing_game_raises(self) -> None:
        def fetcher(url: str) -> bytes:
            if url == DSAPI.game_list:
                return b'{"games":[]}'
            raise AssertionError("unexpected url")

        DSAPI._game_list_cache = None
        api = DSAPI("does-not-exist", fetcher=fetcher)

        with self.assertRaises(ValueError):
            api.download_content(ContentTypes.OFFSETS)


if __name__ == "__main__":
    unittest.main()
