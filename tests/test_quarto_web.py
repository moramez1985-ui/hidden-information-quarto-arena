import http.client
import json
import threading
import unittest

from quarto_web import create_server


class QuartoWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server(0)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2)

    def setUp(self):
        status, _ = self.request(
            "POST",
            "/api/games",
            {"mode": "classic"},
        )
        self.assertEqual(status, 200)

    def request(self, method, path, payload=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        body = None if payload is None else (
            payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        )
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        status = response.status
        response_body = response.read()
        content_type = response.getheader("Content-Type", "")
        connection.close()
        if content_type.startswith("application/json"):
            return status, json.loads(response_body)
        return status, response_body

    def get_state(self):
        status, payload = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        return payload["state"]

    def test_new_game_in_both_modes_and_official_piece_mapping(self):
        for mode in ("classic", "self_selection"):
            with self.subTest(mode=mode):
                status, payload = self.request("POST", "/api/games", {"mode": mode})
                self.assertEqual(status, 200)
                self.assertEqual(payload["state"]["mode"], mode)
                self.assertEqual(payload["state"]["phase"], "select")
                self.assertEqual(payload["state"]["active_player"], "player_1")

        status, payload = self.request("GET", "/api/pieces")
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["pieces"]), 16)
        self.assertEqual(
            [piece["id"] for piece in payload["pieces"]],
            list(range(16)),
        )
        self.assertEqual(len({tuple(piece["attributes"]) for piece in payload["pieces"]}), 16)

    def test_valid_action_updates_state_from_engine(self):
        status, payload = self.request(
            "POST",
            "/api/actions",
            {
                "kind": "select_piece",
                "player": "player_1",
                "piece_id": 5,
                "cell": None,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["state"]["phase"], "place")
        self.assertEqual(payload["state"]["selected_piece"], 5)
        self.assertEqual(payload["state"]["active_player"], "player_2")

    def test_invalid_action_does_not_change_state(self):
        before = self.get_state()
        status, payload = self.request(
            "POST",
            "/api/actions",
            {
                "kind": "select_piece",
                "player": "player_2",
                "piece_id": 5,
                "cell": None,
            },
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "invalid_action")
        self.assertEqual(self.get_state(), before)

    def test_malformed_json_and_invalid_mode_do_not_change_state(self):
        before = self.get_state()
        status, payload = self.request("POST", "/api/games", b"{")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "invalid_json")

        status, payload = self.request("POST", "/api/games", {"mode": "unknown"})
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "invalid_mode")
        self.assertEqual(self.get_state(), before)

    def test_unknown_routes_and_non_ui_files_are_not_served(self):
        for path in (
            "/missing-resource",
            "/quarto_engine.py",
            "/.git/config",
            "/.env",
            "/tests/test_quarto_web.py",
            "/web3-project-mohammad-ramezani.rar",
            "/images/gray-velvet.webp",
        ):
            with self.subTest(path=path):
                status, payload = self.request("GET", path)
                self.assertEqual(status, 404)
                self.assertNotIn("Traceback", json.dumps(payload))

        status, payload = self.request("GET", "/%2e%2e/quarto_engine.py")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "invalid_path")


if __name__ == "__main__":
    unittest.main()
