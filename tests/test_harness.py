from os import environ
import unittest
from unittest.mock import MagicMock, patch

from requests.exceptions import ConnectionError, Timeout

from harness import (
    ApiError,
    HarnessClient,
    _normalize_host,
    entity_id,
    reset_client,
)
import harness
from costcategories import CostCategory
from perspectives.common import Folder
from perspectives.perspective import list_perspectives


class NormalizeHostTest(unittest.TestCase):
    def test_strips_scheme_and_path(self):
        self.assertEqual(_normalize_host("https://app.harness.io/gateway"), "app.harness.io")
        self.assertEqual(_normalize_host("app.harness.io"), "app.harness.io")
        self.assertEqual(_normalize_host("http://localhost:8181/"), "localhost:8181")


class HarnessClientTest(unittest.TestCase):
    def setUp(self):
        reset_client()
        self.session = MagicMock()
        self.client = HarnessClient(
            account="acct",
            host="https://app.harness.io",
            api_key="key",
            session=self.session,
        )

    def tearDown(self):
        reset_client()

    def test_url_builds_gateway_paths(self):
        self.assertEqual(
            self.client.url("budgets"),
            "https://app.harness.io/gateway/ccm/api/budgets",
        )
        self.assertEqual(
            self.client.url("ccm/api/business-mapping"),
            "https://app.harness.io/gateway/ccm/api/business-mapping",
        )

    def test_request_raises_api_error(self):
        response = MagicMock()
        response.ok = False
        response.status_code = 400
        response.text = "bad"
        self.session.request.return_value = response
        with self.assertRaises(ApiError) as caught:
            self.client.request("GET", "budgets")
        self.assertEqual(caught.exception.status, 400)

    def test_retries_transient_status_then_succeeds(self):
        failing = MagicMock(ok=False, status_code=503, text="busy", content=b"")
        ok = MagicMock(ok=True, status_code=200, content=b'{"data":[]}')
        ok.json.return_value = {"data": []}
        self.session.request.side_effect = [failing, ok]
        with patch("harness.sleep"):
            body = self.client.request("GET", "budgets", retries=2)
        self.assertEqual(body, {"data": []})
        self.assertEqual(self.session.request.call_count, 2)

    def test_direct_cost_category_lookup_skips_the_gateway_prefix(self):
        self.assertEqual(
            self.client.url("ccm/api/business-mapping", via_gateway=False),
            "https://app.harness.io/ccm/api/business-mapping",
        )

    def test_timeout_and_connection_errors_become_api_errors(self):
        self.session.request.side_effect = Timeout("slow")
        with patch("harness.sleep"):
            with self.assertRaises(ApiError):
                self.client.request("GET", "budgets", retries=0)
        self.session.request.side_effect = ConnectionError("down")
        with patch("harness.sleep"):
            with self.assertRaises(ApiError):
                self.client.request("GET", "budgets", retries=0)

    def test_does_not_retry_client_errors(self):
        response = MagicMock(ok=False, status_code=404, text="missing")
        self.session.request.return_value = response
        with self.assertRaises(ApiError):
            self.client.request("GET", "budgets", retries=3)
        self.assertEqual(self.session.request.call_count, 1)


class EntityIdTest(unittest.TestCase):
    def test_string_data_is_the_created_id(self):
        self.assertEqual(
            entity_id({"status": "SUCCESS", "data": "I176fw7dR76cFBs_lWJwyQ"}),
            "I176fw7dR76cFBs_lWJwyQ",
        )

    def test_nested_uuid_still_wins(self):
        self.assertEqual(entity_id({"resource": {"uuid": "abc"}}), "abc")
        self.assertEqual(entity_id({"uuid": "top", "data": "nested"}), "top")

    def test_list_data_is_not_an_id(self):
        self.assertIsNone(entity_id({"data": [{"uuid": "abc"}]}))


class ExampleClientContractTest(unittest.TestCase):
    def setUp(self):
        reset_client()
        self.session = MagicMock()
        self.env = patch.dict(
            environ,
            {
                "HARNESS_ACCOUNT_ID": "acct",
                "HARNESS_URL": "https://app.harness.io",
                "HARNESS_PLATFORM_API_KEY": "key",
            },
        )
        self.env.start()
        harness._CLIENT = HarnessClient(session=self.session)

    def tearDown(self):
        self.env.stop()
        reset_client()

    def _ok(self, body):
        response = MagicMock(ok=True, status_code=200, content=b"{}")
        response.json.return_value = body
        return response

    def test_category_lookup_and_boolean_writes(self):
        self.session.request.side_effect = [
            self._ok(
                {
                    "resource": {
                        "businessMappings": [{"name": "Product", "uuid": "cc-1"}]
                    }
                }
            ),
            self._ok({"resource": {"costTargets": [{"name": "hosted"}]}}),
            self._ok({"resource": {"uuid": "cc-1"}}),
            self._ok({"resource": {"businessMappings": []}}),
            self._ok({"resource": {"uuid": "created"}}),
        ]
        category = CostCategory("Product")
        body = category.get()
        self.assertEqual(body["resource"]["costTargets"][0]["name"], "hosted")
        self.assertIs(category.update(), True)
        created = CostCategory("Fresh")
        self.assertIs(created.create(), True)
        self.assertEqual(created.uuid, "created")
        urls = [call.args[1] for call in self.session.request.call_args_list]
        self.assertEqual(urls[0], "https://app.harness.io/ccm/api/business-mapping")
        self.assertEqual(
            urls[1], "https://app.harness.io/ccm/api/business-mapping/cc-1"
        )
        self.assertIn("/gateway/ccm/api/business-mapping", urls[2])
        self.assertIn("/gateway/ccm/api/business-mapping", urls[4])

    def test_folder_create_keeps_the_gateway_uuid(self):
        self.session.request.side_effect = [
            self._ok({"data": []}),
            self._ok({"data": {"uuid": "folder-1"}}),
        ]
        folder = Folder("Product", create=True)
        self.assertEqual(folder.uuid, "folder-1")
        urls = [call.args[1] for call in self.session.request.call_args_list]
        self.assertIn("gateway/ccm/api/perspectiveFolders/create", urls[1])


class PerspectivePagingTest(unittest.TestCase):
    def test_list_perspectives_reads_every_full_page(self):
        first = [{"name": f"view-{index}", "uuid": str(index)} for index in range(100)]
        pages = [
            {"data": {"views": first, "totalCount": 101}},
            {"data": {"views": [{"name": "last", "uuid": "last"}], "totalCount": 101}},
        ]
        with patch("perspectives.perspective.request", side_effect=pages) as requested:
            found = list_perspectives()
        self.assertEqual(requested.call_count, 2)
        self.assertEqual(len(found), 101)
        self.assertIn("last", found)


if __name__ == "__main__":
    unittest.main()
