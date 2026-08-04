import unittest

from src.converters.graphics import _cn_name, _expand, _names


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

    def test_new_graphics_fields_have_chinese_names(self) -> None:
        names = _names()
        attrs = [
            "ContactShadowThickness",
            "DetailSDFShadowRange",
            "ExpandDrawArea",
            "LowQualitySDFShadow",
            "PaniniEnable",
            "ParticleLightingResolution",
            "PresentSkipTimerAfterHomeMenu",
            "ShadowCastFur",
            "DynamicResolution_ManualResolution",
            "ShadowDistance_CullingScaler",
            "StreamingMeshLimit_DownVramThresholdMB",
            "StreamingMeshLimit_UpVramThresholdMB",
        ]

        self.assertTrue(all(_cn_name(attr, names) != attr for attr in attrs))


if __name__ == "__main__":
    unittest.main()
