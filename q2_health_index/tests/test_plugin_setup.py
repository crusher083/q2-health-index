import unittest

from q2_health_index.plugin_setup import plugin as health_index_plugin


class PluginSetupTests(unittest.TestCase):

    def test_plugin_setup(self):
        self.assertEqual(health_index_plugin.name, 'health-index')
