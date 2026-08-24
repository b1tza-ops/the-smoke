import unittest

from utils.rate_limit import FixedWindowRateLimiter


class RateLimiterTests(unittest.TestCase):
    def test_limit_blocks_until_window_expires(self):
        now = [100.0]
        limiter = FixedWindowRateLimiter(
            clock=lambda: now[0]
        )

        self.assertTrue(
            limiter.allow("login:ip", 2, 60)
        )
        self.assertTrue(
            limiter.allow("login:ip", 2, 60)
        )
        self.assertFalse(
            limiter.allow("login:ip", 2, 60)
        )

        now[0] = 161.0
        self.assertTrue(
            limiter.allow("login:ip", 2, 60)
        )


if __name__ == "__main__":
    unittest.main()
