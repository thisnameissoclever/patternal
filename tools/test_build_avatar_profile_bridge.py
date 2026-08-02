from __future__ import annotations

import unittest

from tools.build_avatar_profile_bridge import build_bridge


class BuildAvatarProfileBridgeTests(unittest.TestCase):
    def test_profile_replaces_existing_values_and_adds_new_controls(self) -> None:
        bridge = {
            "body": {
                "measurements": [
                    {
                        "key": "height",
                        "label": "Standing height",
                        "value": 160,
                        "unit": "cm",
                        "origin": "baseline",
                    }
                ]
            }
        }
        profile = {
            "measurements": {
                "height": 167.0,
                "bustSupport": 100.0,
            },
            "measurementOrigins": {"height": "manual"},
        }

        result = build_bridge(bridge, profile)
        by_key = {
            item["key"]: item
            for item in result["body"]["measurements"]
        }

        self.assertEqual(167.0, by_key["height"]["value"])
        self.assertEqual("Standing height", by_key["height"]["label"])
        self.assertEqual("manual", by_key["height"]["origin"])
        self.assertEqual(100.0, by_key["bustSupport"]["value"])
        self.assertEqual("%", by_key["bustSupport"]["unit"])
        self.assertEqual("Supported bust shaping", by_key["bustSupport"]["label"])


if __name__ == "__main__":
    unittest.main()
