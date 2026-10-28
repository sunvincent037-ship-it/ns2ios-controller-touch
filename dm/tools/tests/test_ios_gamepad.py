"""iOS input wiring contracts; behavioral slot/layout tests live in t_ios_pad.c."""
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]


class IosGamepadWiring(unittest.TestCase):
    maxDiff = 300
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'dm/ios/Sources/DmGamepad.m').read_text(encoding='utf-8')

    def test_physical_input_is_published_to_its_own_player(self):
        read = self.source.split('static void read_pad(')[1].split('- (void)padsChanged:')[0]
        self.assertIn('pad_slot_of(&g_slots', read)
        self.assertIn('dm_pad_set_player(p,', read)
        self.assertNotIn('dm_input_set(', read)

    def test_connected_players_are_reported_to_the_game(self):
        self.assertIn('dm_pad_players(pad_slot_mask(&g_slots))', self.source)
        self.assertIn('dm_motion_attach(c, p)', self.source)
        self.assertIn('dm_haptics_apple_controller(p,', self.source)

    def test_hidden_overlay_keeps_its_touch_switch(self):
        self.assertIn('_swap = shape(self.layer)', self.source)
        began = self.source.split('- (void)touchesBegan:')[1].split('- (void)touchesMoved:')[0]
        self.assertLess(began.index('[self inSwap:p]'), began.index('if (_padOff)'))

    def test_background_reset_clears_each_physical_player(self):
        reset = self.source.split('void dm_gamepad_reset(void)')[1]
        self.assertIn('p < DM_PLAYERS', reset)
        self.assertIn('dm_pad_set_player(p, 0, 0, 0, 0, 0)', reset)


if __name__ == '__main__':
    unittest.main()
