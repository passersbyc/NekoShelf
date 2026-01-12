import unittest
from core.utils import parse_id_ranges, parse_status, parse_tags_to_list

class TestUtils(unittest.TestCase):
    def test_parse_id_ranges(self):
        self.assertEqual(parse_id_ranges("1,2,3"), [1, 2, 3])
        self.assertEqual(parse_id_ranges("1-3"), [1, 2, 3])
        self.assertEqual(parse_id_ranges("1, 3-5"), [1, 3, 4, 5])
        self.assertEqual(parse_id_ranges("5-1"), [1, 2, 3, 4, 5])
        self.assertEqual(parse_id_ranges("1,1,2"), [1, 2])

    def test_parse_status(self):
        self.assertEqual(parse_status("完结"), 1)
        self.assertEqual(parse_status("连载"), 0)
        self.assertEqual(parse_status("done"), 1)
        self.assertEqual(parse_status("ongoing"), 0)
        self.assertEqual(parse_status("2"), 2)
        self.assertEqual(parse_status(None), None)

    def test_parse_tags_to_list(self):
        self.assertEqual(parse_tags_to_list("tag1, tag2"), ["tag1", "tag2"])
        self.assertEqual(parse_tags_to_list("tag1 tag2"), ["tag1", "tag2"])
        self.assertEqual(parse_tags_to_list("#tag1 #tag2"), ["tag1", "tag2"])
        self.assertEqual(parse_tags_to_list("tag1，tag2"), ["tag1", "tag2"])
        self.assertEqual(parse_tags_to_list(""), [])

if __name__ == '__main__':
    unittest.main()
