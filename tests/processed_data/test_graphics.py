import unittest

from src.processed_data.graphics.exporter import _expand


class GraphicsPresetTests(unittest.TestCase):
    def test_expand_supports_new_graphics_preset_fields(self) -> None:
        row = {
            "ContactShadowThickness": 0.05,
            "DynamicResolutionMode": 12,
            "ShadowCastDistanceType": 3,
            "StreamingMeshMinimumLOD": 1,
        }
        root = {
            "_DynamicResolutionParamList": [
                {
                    "Mode": 12,
                    "ManualResolution": [[1920.0, 1080.0], [1280.0, 720.0]],
                }
            ],
            "_ShadowDistanceSettings": [
                {
                    "Type": 3,
                    "CascadeNum": 2,
                    "DynamicShadowCascadeRange": 2,
                    "WorldPartition": [6.0, 20.0, 30.0, 40.0],
                    "CullingScaler": [1.0, 1.0, 2.0, 4.0],
                }
            ],
            "_StreamingMeshLimitList": [
                {
                    "StreamingMeshMinimumLodLimit": 1,
                    "DownVramThresholdMB": 800,
                    "UpVramThresholdMB": 650,
                }
            ],
        }

        expanded = _expand(row, root)

        self.assertEqual(expanded["ContactShadowThickness"], 0.05)
        self.assertEqual(
            expanded["DynamicResolution_ManualResolution"],
            "[[1920.0, 1080.0], [1280.0, 720.0]]",
        )
        self.assertEqual(expanded["ShadowDistance_CascadeNum"], 2)
        self.assertEqual(expanded["ShadowDistance_DynamicShadowCascadeRange"], 2)
        self.assertEqual(
            expanded["ShadowDistance_WorldPartition"],
            "[6.0, 20.0, 30.0, 40.0]",
        )
        self.assertEqual(
            expanded["ShadowDistance_CullingScaler"],
            "[1.0, 1.0, 2.0, 4.0]",
        )
        self.assertEqual(expanded["StreamingMeshLimit_DownVramThresholdMB"], 800)
        self.assertEqual(expanded["StreamingMeshLimit_UpVramThresholdMB"], 650)

    def test_expand_keeps_legacy_vram_threshold_compatible(self) -> None:
        expanded = _expand(
            {"StreamingMeshMinimumLOD": 1},
            {
                "_StreamingMeshLimitList": [
                    {
                        "StreamingMeshMinimumLodLimit": 1,
                        "VramThresholdMB": 600,
                    }
                ]
            },
        )

        self.assertEqual(expanded["StreamingMeshLimit_VramThresholdMB"], 600)


if __name__ == "__main__":
    unittest.main()
