"""Unit tests for the /api/ai/chat route helpers (no server needed)."""

from __future__ import annotations

from featcat.server.routes.ai import _is_multipart


class TestIsMultipart:
    def test_single_question_returns_false(self):
        assert _is_multipart("Catalog có bao nhiêu features?") is False

    def test_short_query_with_numbers_returns_false(self):
        # Under 80 chars, even with stray "1)" — too short to be a real list.
        assert _is_multipart("Cho tôi 1) info") is False

    def test_two_numbered_items_returns_false(self):
        # Only 2 distinct numbers — single follow-up, not a list.
        q = "Tôi cần xem: 1) features về network, và 2) drift status. Cảm ơn bạn rất nhiều."
        assert _is_multipart(q) is False

    def test_three_numbered_items_returns_true(self):
        q = (
            "Tôi đang xây pipeline ML lớn. Cần: 1) liệt kê features, "
            "2) check drift, 3) gợi ý feature engineering. Cảm ơn."
        )
        assert _is_multipart(q) is True

    def test_seven_numbered_items_returns_true(self):
        q = (
            "Tôi cần: 1) liệt kê tất cả features, 2) check drift, 3) gợi ý "
            "feature engineering, 4) so sánh device_logs với client_logs, "
            "5) tìm duplicate trong demand_v2, 6) tóm tắt health, 7) recommend"
        )
        assert _is_multipart(q) is True

    def test_dot_separator_also_works(self):
        q = (
            "Help me with: 1. list features, 2. check drift, 3. recommend top "
            "5 for churn. Need this for a customer demo tomorrow."
        )
        assert _is_multipart(q) is True

    def test_repeated_same_number_returns_false(self):
        # Three "1)" markers shouldn't count — must be distinct numbers.
        q = (
            "Bullet one says 1) thing one and bullet 1) thing two and "
            "also 1) thing three is some more random padding text here ok."
        )
        assert _is_multipart(q) is False
