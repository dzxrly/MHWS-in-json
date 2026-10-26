"""Large research models retain every value when whitespace is removed."""

import json
from unittest import TestCase
from unittest.mock import patch

from sdk.enemy_logic_exporter.shared.models.io import encode_model


class ModelEncodingTests(TestCase):
    def test_compact_encoding_preserves_complete_object(self):
        model = dict(items=[dict(v=i) for i in range(8)])
        with patch("sdk.enemy_logic_exporter.shared.models.io.MODEL_LIMIT_BYTES", 120):
            content = encode_model(model)
        self.assertLessEqual(len(content.encode("utf8")), 120)
        self.assertEqual(json.loads(content), model)

    def test_oversize_compact_model_still_requires_sharding(self):
        with patch("sdk.enemy_logic_exporter.shared.models.io.MODEL_LIMIT_BYTES", 20):
            with self.assertRaisesRegex(ValueError, "分片"):
                encode_model(dict(text="large" * 20))
