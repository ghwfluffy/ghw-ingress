import copy
import unittest

from render_config import ConfigError, normalize_config, build_static_config, build_dynamic_config


class TcpRoutesTest(unittest.TestCase):
    def config(self):
        return {"version": 1, "ingress": {"acme": {"email": "ops@example.test"}},
                "routes": [{"name": "site", "host": "example.test", "target": "http://web:8000"}],
                "tcp_routes": [{"name": "devices", "port": 9443, "server_name": "example.test", "target": "devices:9443"}]}

    def test_tls_is_passed_through_and_separate_from_http(self):
        config = normalize_config(self.config())
        self.assertEqual(build_static_config(config)["entryPoints"]["tcp-devices"], {"address": ":9443"})
        tcp = build_dynamic_config(config)["tcp"]
        self.assertEqual(tcp["routers"]["tcp-devices"]["tls"], {"passthrough": True})
        self.assertEqual(tcp["routers"]["tcp-devices"]["rule"], "HostSNI(`example.test`)")
        self.assertEqual(tcp["services"]["tcp-devices"]["loadBalancer"]["servers"], [{"address": "devices:9443"}])

    def test_invalid_values_and_port_collisions_are_rejected(self):
        for key, value in [("name", "site"), ("name", "bad`name"), ("port", 80), ("port", 443),
                           ("port", True), ("port", 65536), ("server_name", "*"),
                           ("server_name", "example.test`"),
                           ("target", "http://devices:9443"), ("target", "devices:99999")]:
            raw = self.config()
            raw["tcp_routes"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ConfigError):
                normalize_config(raw)
        raw = self.config()
        duplicate = copy.deepcopy(raw["tcp_routes"][0])
        duplicate["name"] = "another-device"
        raw["tcp_routes"].append(duplicate)
        with self.assertRaises(ConfigError):
            normalize_config(raw)

    def test_existing_configs_do_not_get_tcp_routers(self):
        raw = self.config()
        del raw["tcp_routes"]
        self.assertNotIn("tcp", build_dynamic_config(normalize_config(raw)))


if __name__ == '__main__':
    unittest.main()
