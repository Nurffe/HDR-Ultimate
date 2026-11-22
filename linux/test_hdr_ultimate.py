"""Tests for the parts that don't need a Linux desktop. Run: python -m unittest test_hdr_ultimate"""
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import hdr_ultimate as h
from hdr_ultimate import Game, GameConfig, KdeBackend, Monitor, OledCare

# Shape of kscreen-doctor -o, from libkscreen's doctor.cpp, with its colour codes.
KDE_TEXT = (
    "\x1b[01;32mOutput: \x1b[0;0m1 DP-1 abc-uuid\n"
    "\tenabled\n\tconnected\n\tpriority 1\n"
    "\x1b[01;33m\tHDR: \x1b[0;0menabled\n"
    "\x1b[01;33m\tWide Color Gamut: \x1b[0;0menabled\n"
    "\x1b[01;33m\tVrr: \x1b[0;0mAlways\n"
    "\x1b[01;32mOutput: \x1b[0;0m2 DP-2 def-uuid\n"
    "\x1b[01;33m\tHDR: \x1b[0;0mdisabled\n"
    "\x1b[01;33m\tVrr: \x1b[0;0mNever\n"
    "\x1b[01;32mOutput: \x1b[0;0m3 HDMI-A-1 ghi-uuid\n"
    "\x1b[01;33m\tHDR: \x1b[0;0mincapable\n"
    "\x1b[01;33m\tVrr: \x1b[0;0mincapable\n"
    # A fourth output whose kscreen-doctor prints no Vrr: line at all (older Plasma):
    # the monitor must read as VRR-incapable rather than borrowing a neighbour's policy.
    "\x1b[01;32mOutput: \x1b[0;0m4 DP-3 jkl-uuid\n"
    "\x1b[01;33m\tHDR: \x1b[0;0mdisabled\n"
)


def mode(mode_id, current):
    return (mode_id, 2560, 1440, 144.0, 1.0, [1.0], {"is-current": current} if current else {})


GNOME_STATE = (
    42,
    [(("DP-1", "ACR", "X27U", "1"), [mode("a60", False), mode("a144", True)],
      {"display-name": "X27U", "color-mode": 0, "supported-color-modes": [0, 1]}),
     (("DP-2", "ACR", "VG270U", "2"), [mode("b144", True)],
      {"display-name": "VG270U", "color-mode": 1, "supported-color-modes": [0, 1]}),
     (("HDMI-1", "OLD", "TV", "3"), [mode("c60", True)], {"display-name": "TV"})],
    [(0, 0, 1.0, 0, True, [("DP-1", "ACR", "X27U", "1")], {}),
     (2560, 0, 1.25, 0, False, [("DP-2", "ACR", "VG270U", "2")], {}),
     (5120, 0, 1.0, 1, False, [("HDMI-1", "OLD", "TV", "3")], {})],
    {"layout-mode": 1},
)


class Parsing(unittest.TestCase):
    def test_kde(self):
        m = KdeBackend.parse(KDE_TEXT)
        self.assertEqual([x.id for x in m], ["DP-1", "DP-2", "HDMI-A-1", "DP-3"])
        self.assertEqual([(x.hdr_supported, x.hdr_on) for x in m],
                         [(True, True), (True, False), (False, False), (True, False)])

    def test_kde_vrr_parse(self):
        m = KdeBackend.parse(KDE_TEXT)
        self.assertEqual([(x.vrr_supported, x.vrr_policy, x.vrr_on) for x in m], [
            (True, "always", True), (True, "never", False), (False, "", False), (False, "", False)])

    def test_other_backends_refuse_vrr(self):
        gnome = h.GnomeBackend.__new__(h.GnomeBackend)
        self.assertFalse(gnome.manages_vrr)
        self.assertFalse(gnome.set_vrr(Monitor("DP-1", "X"), "always"))
        none = h.NoBackend()
        self.assertFalse(none.manages_vrr)
        self.assertFalse(none.set_vrr(Monitor("DP-1", "X"), "always"))
        self.assertTrue(h.KdeBackend.manages_vrr)

    def test_gnome_read(self):
        m = h.gnome_monitors(GNOME_STATE)
        self.assertEqual([(x.id, x.hdr_supported, x.hdr_on) for x in m],
                         [("DP-1", True, False), ("DP-2", True, True), ("HDMI-1", False, False)])

    def test_gnome_keeps_layout(self):
        serial, method, logical, props = h.gnome_config(GNOME_STATE, "DP-1", True, lambda v: v)
        self.assertEqual((serial, method, props), (42, 1, {"layout-mode": 1}))
        self.assertEqual(logical, [
            (0, 0, 1.0, 0, True, [("DP-1", "a144", {"color-mode": 1})]),
            (2560, 0, 1.25, 0, False, [("DP-2", "b144", {"color-mode": 1})]),  # stays on
            (5120, 0, 1.0, 1, False, [("HDMI-1", "c60", {})]),
        ])

    def test_kde_commands_drop_the_x11_platform(self):
        def env_for(platform):
            return mock.patch.dict(os.environ, {"QT_QPA_PLATFORM": platform, "KEEP": "1"})

        with env_for("xcb;wayland"):
            env = KdeBackend.env()
            self.assertNotIn("QT_QPA_PLATFORM", env)
            self.assertEqual(env["KEEP"], "1")
            self.assertEqual(os.environ["QT_QPA_PLATFORM"], "xcb;wayland")
        with env_for("xcb"):
            self.assertNotIn("QT_QPA_PLATFORM", KdeBackend.env())
        with env_for("wayland-egl"):
            self.assertEqual(KdeBackend.env()["QT_QPA_PLATFORM"], "wayland-egl")
        with mock.patch.dict(os.environ, {"KEEP": "1"}, clear=False):
            os.environ.pop("QT_QPA_PLATFORM", None)
            self.assertNotIn("QT_QPA_PLATFORM", KdeBackend.env())

        run = mock.Mock(return_value=mock.Mock(stdout=KDE_TEXT, stderr="", returncode=0))
        burst = mock.Mock()
        backend = KdeBackend()
        with env_for("xcb;wayland"), mock.patch.object(h.subprocess, "run", run), mock.patch.object(h.subprocess, "Popen", burst):
            self.assertEqual([m.id for m in backend.monitors()], ["DP-1", "DP-2", "HDMI-A-1", "DP-3"])
            backend.set_hdr(backend.last[0], True)
            backend.set_mode(backend.last[0], (2560, 1440, 144))
        self.assertEqual(run.call_count, 2)
        self.assertEqual(burst.call_count, 1)
        for call in list(run.call_args_list) + list(burst.call_args_list):
            self.assertNotIn("QT_QPA_PLATFORM", call.kwargs["env"])
            self.assertEqual(call.kwargs["env"]["KEEP"], "1")
        self.assertEqual(run.call_args_list[0].args[0], ["kscreen-doctor", "-o"])

        quiet = mock.Mock(return_value=mock.Mock(stdout="", stderr="", returncode=0))
        with env_for("xcb"), mock.patch.object(h.subprocess, "run", quiet), mock.patch.object(h, "log") as logged:
            backend = KdeBackend()
            self.assertEqual(backend.monitors(), [])
            backend.monitors()
            self.assertEqual(logged.call_count, 1)
            self.assertIn("no outputs", logged.call_args.args[0])
            quiet.return_value = mock.Mock(stdout=KDE_TEXT, stderr="", returncode=0)
            backend.monitors()
            quiet.return_value = mock.Mock(stdout="", stderr="", returncode=0)
            backend.monitors()
            self.assertEqual(logged.call_count, 2)

    def test_kde_modes(self):
        text = KDE_TEXT.replace("\tenabled\n", "\tenabled\n\x1b[01;33m\tModes: \x1b[0;0m 1:2560x1440@144*!  2:2560x1440@59.95  3:1920x1080@60  \n", 1)
        m = KdeBackend.parse(text)[0]
        self.assertEqual(m.current, (2560, 1440, 144))
        self.assertEqual(m.modes, [(2560, 1440, 144), (2560, 1440, 60), (1920, 1080, 60)])
        self.assertEqual(m.mode_ids[(2560, 1440, 60)], "2")

    def test_pick_mode(self):
        m = Monitor("DP-1", "X", modes=[(2560, 1440, 144), (2560, 1440, 60), (1920, 1080, 60)], current=(2560, 1440, 144))
        self.assertEqual(h.pick_mode(m, 1920, 1080, 0), (1920, 1080, 60))   # 144 not offered there: fastest it has
        self.assertEqual(h.pick_mode(m, 0, 0, 60), (2560, 1440, 60))        # refresh only
        self.assertEqual(h.pick_mode(m, 1920, 1080, 144), (1920, 1080, 60))  # 144 not offered: the fastest below it
        self.assertIsNone(h.pick_mode(m, 1920, 1080, 30))                   # nothing at or below 30
        self.assertIsNone(h.pick_mode(m, 1280, 720, 0))                     # resolution not offered

    def test_gnome_mode_change_moves_neighbours(self):
        first = h.gnome_monitors(GNOME_STATE)[0]  # two 144 Hz modes: the current one's id wins
        self.assertEqual((first.modes, first.current, first.mode_ids), ([(2560, 1440, 144)], (2560, 1440, 144), {(2560, 1440, 144): "a144"}))
        state = (GNOME_STATE[0], [(GNOME_STATE[1][0][0], GNOME_STATE[1][0][1] + [("a1080", 1920, 1080, 60.0, 1.0, [1.0], {})],
                                   GNOME_STATE[1][0][2])] + GNOME_STATE[1][1:], GNOME_STATE[2], GNOME_STATE[3])
        _, _, logical, _ = h.gnome_config(state, "DP-1", None, lambda v: v, "a1080")
        self.assertEqual([(lm[0], lm[5][0][1]) for lm in logical], [(0, "a1080"), (1920, "b144"), (4480, "c60")])
        self.assertEqual(logical[0][5][0][2], {"color-mode": 0})  # colour mode untouched

    def test_in_game_resolution(self):
        cases = [
            ('{ "name": "Resolution", "type": "string_list", "value": "2560x1440", "index": 20 }', '"value": "1920x1080"'),
            ('<screenWidth value="2560" />\n<screenHeight value="1440" />\n<resolutionIndexWindowed value="20" />',
             '<screenWidth value="1920" />\n<screenHeight value="1080" />\n<resolutionIndexWindowed value="20" />'),
            ("ResolutionSizeX=2560\nResolutionSizeY=1440\nWindowPosX=-1\nFrameRateLimit=240.000000",
             "ResolutionSizeX=1920\nResolutionSizeY=1080\nWindowPosX=-1\nFrameRateLimit=240.000000"),
        ]
        for text, expected in cases:
            out, found = GameConfig.replace_resolution(text, 1920, 1080)
            self.assertIn(expected, out)
            self.assertGreater(found, 0)
        self.assertEqual(GameConfig.replace_resolution("MaxFPS=240\nTextureWidth=2048", 1920, 1080)[1], 0)

    def test_paths(self):
        self.assertEqual(h.file_name(r"Z:\games\Foo.exe"), "Foo.exe")
        self.assertEqual(h.file_name("/games/foo/Foo.exe"), "Foo.exe")

    def test_game_settings(self):
        self.assertIs(GameConfig.parse('{ "name": "HDRModes", "type": "x", "value": "HDR10 PQ" }'), True)
        self.assertIs(GameConfig.parse('{ "name": "HDRModes", "value": "None" }'), False)
        self.assertIs(GameConfig.parse("bUseHDRDisplayOutput=True\nHDRBrightness=300"), True)
        self.assertIsNone(GameConfig.parse("HDRBrightness=300"))

    def test_process_match(self):
        g = Game(exe="/games/hl/HogwartsLegacy.exe")
        self.assertTrue(h.owns_process(g, ["python", r"Z:\games\hl\HogwartsLegacy.exe"]))
        self.assertTrue(h.owns_process(g, ["/games/hl/Phoenix/Binaries/Win64/Real.exe"]))
        self.assertFalse(h.owns_process(g, ["/usr/bin/firefox"]))


class Oled(unittest.TestCase):
    def setUp(self):
        self.care = OledCare()
        self.game = Game(exe="/g/a.exe", oled_care=True, monitors={"DP-1": "X"})
        self.on = [Monitor("DP-1", "X", True, True)]
        self.off = [Monitor("DP-1", "X", True, False)]

    def tick(self, now, mons, focused, running=True, enabled=True):
        return self.care.tick(now, mons, [self.game] if running else [], self.game if focused else None, enabled, 60)

    def test_off_after_limit_then_back(self):
        self.tick(0, self.on, True)
        self.assertEqual(self.tick(59, self.on, False), ([], []))
        self.assertEqual(self.tick(61, self.on, False)[1], self.on)
        self.assertEqual(self.tick(63, self.off, False), ([], []))
        self.assertEqual(self.tick(65, self.off, True)[0], self.off)

    def test_native_wayland_game_never_seen_focused_is_left_alone(self):
        for t in range(0, 600, 30):
            self.assertEqual(self.tick(t, self.on, False), ([], []))

    def test_opted_out_game_is_ignored(self):
        self.game.oled_care = False
        self.tick(0, self.on, True)
        self.assertEqual(self.tick(600, self.on, False), ([], []))

    def test_turned_on_by_hand_stays_on_while_tabbed_out(self):
        self.tick(0, self.on, True)
        self.tick(61, self.on, False)
        self.assertEqual(self.tick(200, self.on, False), ([], []))

    def test_master_switch_off_restores(self):
        self.tick(0, self.on, True)
        self.tick(61, self.on, False)
        self.assertEqual(self.tick(63, self.off, False, enabled=False)[0], self.off)

    def test_game_closed_leaves_hdr_off(self):
        self.tick(0, self.on, True)
        self.tick(61, self.on, False)
        self.assertEqual(self.tick(63, self.off, False, running=False), ([], []))
        self.assertEqual(self.care.off, set())


class UsageCheckIn(unittest.TestCase):
    def test_once_a_day_nothing_else_and_opt_out(self):
        import os
        import threading
        import time
        from http.server import BaseHTTPRequestHandler, HTTPServer

        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append((self.path, dict(self.headers), self.rfile.read(int(self.headers["Content-Length"] or 0))))
                self.send_response(204)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        os.environ[h.Usage.TEST_VARIABLE] = "http://127.0.0.1:%d/ping" % server.server_port
        channel, h.Build.channel = h.Build.channel, "dev"
        try:
            def run(config):
                usage = h.Usage()
                config.save = lambda: None
                usage.tick(config)
                while usage.sending:
                    time.sleep(0.01)
                usage.tick(config)  # picks up the finished check-in
                usage.next_try = 0
                usage.tick(config)  # same day: nothing more
                time.sleep(0.2)
                return config

            config = run(h.Config(usage_asked=True))
            self.assertEqual(len(seen), 1)
            path, headers, body = seen[0]
            self.assertEqual((path, headers["User-Agent"], body), ("/ping", "HDRUltimate", b""))
            self.assertTrue(config.usage_day)
            run(h.Config(usage_asked=True, usage_enabled=False))
            run(h.Config(usage_asked=False))
            self.assertEqual(len(seen), 1)
        finally:
            h.Build.channel = channel
            server.shutdown()


class Guard(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.g = h.ModeGuard(clock=lambda: self.now[0])

    def test_spacing(self):
        self.assertTrue(self.g.ready("DP-1"))
        self.assertFalse(self.g.result("DP-1", True, 0.2))
        self.now[0] += 1
        self.assertFalse(self.g.ready("DP-1"))
        self.assertAlmostEqual(self.g.wait("DP-1"), 3.0)
        self.assertAlmostEqual(self.g.wait("DP-2"), 0.5)  # another monitor: the short gap
        self.now[0] += 3
        self.assertTrue(self.g.ready("DP-1"))
        self.g.touched("DP-1")  # HDR switched
        self.assertFalse(self.g.ready("DP-1"))

    def test_switches_off_after_trouble(self):
        self.assertFalse(self.g.result("DP-1", False, 0.1))
        self.assertTrue(self.g.result("DP-1", False, 0.1))  # second failure
        self.assertIn("DP-1", self.g.blocked)
        self.assertFalse(self.g.ready("DP-1"))
        self.assertTrue(self.g.result("DP-2", True, 6.0))  # one slow change is enough
        self.assertFalse(self.g.result("DP-2", True, 6.0))  # reported once
        self.assertFalse(self.g.result("DP-3", False, 0.1))
        self.assertFalse(self.g.result("DP-3", True, 0.1))  # a success clears the count
        self.assertFalse(self.g.result("DP-3", False, 0.1))
        self.assertNotIn("DP-3", self.g.blocked)


class RefreshRates(unittest.TestCase):
    def test_fallback_up_to_480(self):
        offered = [240, 165, 144, 120, 60]
        self.assertEqual(h.fallback_rate(offered, 165), 165)
        self.assertEqual(h.fallback_rate(offered, 480), 240)
        self.assertEqual(h.fallback_rate(offered, 200), 165)
        self.assertEqual(h.fallback_rate(offered, 50), 0)
        self.assertEqual(max(h.COMMON_RATES), 480)

    def test_pick_mode_uses_fallback(self):
        mon = Monitor(id="DP-1", name="X27U", modes=[(2560, 1440, 240), (2560, 1440, 144), (1920, 1080, 240)], current=(2560, 1440, 144))
        self.assertEqual(h.pick_mode(mon, 0, 0, 480), (2560, 1440, 240))
        self.assertEqual(h.pick_mode(mon, 1920, 1080, 360), (1920, 1080, 240))
        self.assertIsNone(h.pick_mode(mon, 0, 0, 30))


class ChoiceLists(unittest.TestCase):
    """The dropdowns' contents as plain data, so what a menu offers can be tested without Qt."""

    def monitor(self, mid, name, connected=True, hdr=True, modes=(), current=None, policy="automatic"):
        mon = Monitor(id=mid, name=name, hdr_supported=hdr, modes=list(modes), current=current, vrr_policy=policy)
        mon.connected = connected
        return mon

    def test_hdr_summary(self):
        self.assertEqual(h.hdr_summary(Game(ask=True)), "Ask")
        self.assertEqual(h.hdr_summary(Game(ask=False)), "On")

    def test_monitor_choices_lists_connected_and_missing(self):
        on, off = self.monitor("DP-1", "XG32", hdr=False), self.monitor("DP-2", "Gone")
        rows = h.monitor_choices({"DP-1": "XG32", "DP-3": "Old"}, [on, off])
        self.assertEqual(rows, [("DP-1", "XG32  — no HDR", True, True),
                                ("DP-2", "Gone", False, True),
                                ("DP-3", "Old  — not connected", True, True)])

    def test_monitor_choices_keep_one(self):
        on, off = self.monitor("DP-1", "XG32"), self.monitor("DP-2", "X27U")
        rows = h.monitor_choices({"DP-1": "XG32"}, [on, off])
        # The only checked monitor can't be unchecked: a game always needs one.
        self.assertEqual([(k, e) for k, _, _, e in rows], [("DP-1", False), ("DP-2", True)])
        rows = h.monitor_choices({"DP-1": "XG32", "DP-2": "X27U"}, [on, off])
        self.assertTrue(all(e for _, _, _, e in rows))

    def test_mode_choices_are_separate_menus(self):
        mon = self.monitor("DP-1", "XG32", modes=[(3840, 2160, 240), (2560, 1440, 480), (2560, 1440, 240)],
                           current=(2560, 1440, 240))
        game = Game(mode_monitor="DP-1", mode_width=2560, mode_height=1440, mode_hz=480)
        choices = h.mode_choices(game, [mon])
        self.assertEqual(choices["monitor"], [("", "Don't change", False, True), ("DP-1", "XG32", True, True)])
        self.assertEqual([(v, c) for v, _, c, _ in choices["resolution"]],
                         [((0, 0), False), ((3840, 2160), False), ((2560, 1440), True)])
        self.assertEqual([v for v, _, _, _ in choices["refresh"]], [0, 480, 240])
        self.assertFalse(choices["in_game"])

    def test_mode_choices_refresh_lists_every_rate(self):
        mon = self.monitor("DP-1", "XG32", modes=[(2560, 1440, 480), (2560, 1440, 240), (1920, 1080, 120)],
                           current=(2560, 1440, 240))
        game = Game(mode_monitor="DP-1", mode_width=1920, mode_height=1080, mode_hz=120)
        rates = [v for v, _, _, _ in h.mode_choices(game, [mon])["refresh"]]
        # The menu is built once, so it lists every rate the monitor has; pick_size pulls the chosen one down.
        self.assertEqual(rates, [0, 480, 240, 120])

    def test_mode_choices_without_a_monitor(self):
        choices = h.mode_choices(Game(), [self.monitor("DP-1", "XG32", modes=[(2560, 1440, 240)])])
        self.assertEqual(choices["resolution"], [])  # nothing to pick until a monitor is chosen
        self.assertEqual(choices["refresh"], [])

    def test_mode_choices_keeps_a_disconnected_choice(self):
        choices = h.mode_choices(Game(mode_monitor="DP-9", mode_width=2560, mode_height=1440), [])
        self.assertIn(("DP-9", "DP-9  — not connected", True, True), choices["monitor"])
        self.assertEqual(choices["resolution"], [])


class UpdateCheck(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(h.parse_version("V1.2"), (1, 2, 0))
        self.assertEqual(h.parse_version("1.3.1"), (1, 3, 1))
        self.assertIsNone(h.parse_version("latest"))
        self.assertIsNone(h.parse_version(None))
        self.assertFalse(h.is_newer("V1.2", "1.3.0"))
        self.assertFalse(h.is_newer("V1.3", "1.3.0"))
        self.assertTrue(h.is_newer("v1.3.1", "1.3.0"))
        self.assertTrue(h.is_newer("V2.0", "1.3.0"))

    def test_mode_summary(self):
        self.assertEqual(h.mode_summary(Game()), "Don't change")
        self.assertEqual(h.mode_summary(Game(mode_monitor="DP-1", mode_width=2560, mode_height=1440, mode_hz=165)), "2560×1440 165Hz")
        self.assertEqual(h.mode_summary(Game(mode_monitor="DP-1", mode_width=1920, mode_height=1080, mode_hz=120, mode_in_game=True)),
                         "1920×1080 120Hz in-game")

    def test_banner_mode_line(self):
        mon = Monitor(id="DP-1", name="X27U", hdr_supported=True, hdr_on=True)
        mon.current = (2560, 1440, 165)
        self.assertIsNone(h.banner_mode_line(None, mon))
        self.assertIsNone(h.banner_mode_line(Game(), mon))
        self.assertIsNone(h.banner_mode_line(Game(mode_monitor="DP-2", mode_hz=144), mon))  # set on another monitor
        self.assertEqual(h.banner_mode_line(Game(mode_monitor="DP-1", mode_width=2560, mode_height=1440, mode_hz=165), mon),
                         "2560 × 1440  ·  165 Hz")
        self.assertEqual(h.banner_mode_line(Game(mode_monitor="DP-1", mode_width=1920, mode_height=1080, mode_in_game=True), mon),
                         "1920 × 1080 in game  ·  165 Hz")

    def test_finds_newer_release_and_only_links_to_github(self):
        import json
        import os
        import threading
        import time
        from http.server import BaseHTTPRequestHandler, HTTPServer

        reply = {}
        agents = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                agents.append(self.headers["User-Agent"])
                body = json.dumps(reply["json"]).encode() if "json" in reply else b"<html>sign in</html>"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        os.environ[h.Updates.TEST_VARIABLE] = "http://127.0.0.1:%d/" % server.server_port
        channel, h.Build.channel = h.Build.channel, "dev"
        try:
            def run(json_reply, config=None):
                if json_reply is None:
                    reply.pop("json", None)
                else:
                    reply["json"] = json_reply
                updates = h.Updates()
                updates.next_try = 0
                config = config or h.Config()
                self.assertFalse(updates.tick(config))
                while updates.checking:
                    time.sleep(0.01)
                return updates, updates.tick(config)

            page = "https://github.com/WillPidgeon/HDR-Ultimate/releases/tag/V9.1"
            updates, found = run({"tag_name": "V9.1", "html_url": page})
            self.assertTrue(found)
            self.assertEqual((updates.latest, updates.page), ("9.1.0", page))
            self.assertEqual(agents[-1], "HDRUltimate")
            updates, found = run({"tag_name": "V9.2", "html_url": "https://evil.example/x"})
            self.assertEqual(updates.page, h.Updates.RELEASES_PAGE)
            self.assertFalse(run({"tag_name": "V1.0", "html_url": page})[1])  # older: nothing
            self.assertFalse(run(None)[1])  # a Wi-Fi sign-in page: nothing
            calls = len(agents)
            self.assertFalse(run({"tag_name": "V9.1"}, h.Config(updates_enabled=False))[1])
            self.assertEqual(len(agents), calls)  # switched off: no request at all
        finally:
            h.Build.channel = channel
            server.shutdown()


class SocketPaths(unittest.TestCase):
    """The single-instance socket must be somewhere only this user can reach (faked Linux file owners)."""

    def paths(self, runtime_uid=1000, runtime_mode=0o700, legacy_uid=None, runtime="/run/user/1000"):
        import os
        from types import SimpleNamespace
        from unittest import mock

        def fake_stat(path):
            if path == runtime:
                return SimpleNamespace(st_uid=runtime_uid, st_mode=0o40000 | runtime_mode)
            raise FileNotFoundError(path)

        def fake_lstat(path):
            if legacy_uid is None:
                raise FileNotFoundError(path)
            return SimpleNamespace(st_uid=legacy_uid)

        env = {"XDG_RUNTIME_DIR": runtime} if runtime else {}
        with mock.patch.object(h.os, "getuid", lambda: 1000, create=True), \
                mock.patch.object(h.os, "stat", fake_stat), mock.patch.object(h.os, "lstat", fake_lstat), \
                mock.patch.object(h.os, "chmod", lambda *a: None), mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(h.Path, "home", lambda: h.Path("/home/me")), \
                mock.patch.object(h.Path, "mkdir", lambda *a, **k: None):
            sock, legacy = h.socket_paths()
        return sock.replace("\\", "/"), legacy and legacy.replace("\\", "/")

    def test_private_runtime_folder(self):
        sock, legacy = self.paths()
        self.assertTrue(sock.startswith("/run/user/1000/hdr-ultimate"), sock)
        self.assertIsNone(legacy)

    def test_runtime_folder_others_can_open_is_not_used(self):
        self.assertTrue(self.paths(runtime_mode=0o755)[0].startswith("/home/me/.cache/hdr-ultimate/"))

    def test_runtime_folder_owned_by_someone_else_is_not_used(self):
        self.assertTrue(self.paths(runtime_uid=0)[0].startswith("/home/me/.cache/hdr-ultimate/"))

    def test_no_runtime_folder(self):
        self.assertTrue(self.paths(runtime=None)[0].startswith("/home/me/.cache/hdr-ultimate/"))

    def test_old_tmp_socket_only_if_ours(self):
        self.assertTrue(self.paths(legacy_uid=1000)[1].endswith("/hdr-ultimate" + h.Build.suffix()))
        self.assertIsNone(self.paths(legacy_uid=1001)[1])

class Vrr(unittest.TestCase):
    def monitor(self, vrr_policy="never", vrr_on=False, supported=True, name="X27U"):
        return Monitor("DP-1", name, vrr_policy=vrr_policy, vrr_on=vrr_on, vrr_supported=supported)

    def test_kde_vrr_command(self):
        backend = KdeBackend()
        burst = mock.Mock()
        with mock.patch.dict(os.environ, {"QT_QPA_PLATFORM": "xcb;wayland", "KEEP": "1"}), \
                mock.patch.object(h.subprocess, "Popen", burst):
            self.assertTrue(backend.set_vrr(self.monitor(), "always"))
            self.assertTrue(backend.set_vrr(self.monitor(), "automatic"))
        self.assertEqual([c.args[0] for c in burst.call_args_list],
                         [["kscreen-doctor", "output.DP-1.vrrpolicy.always"],
                          ["kscreen-doctor", "output.DP-1.vrrpolicy.automatic"]])
        for call in burst.call_args_list:
            self.assertEqual(call.kwargs["stdout"], h.subprocess.DEVNULL)
            self.assertEqual(call.kwargs["stderr"], h.subprocess.DEVNULL)
            self.assertTrue(call.kwargs["start_new_session"])
            self.assertNotIn("QT_QPA_PLATFORM", call.kwargs["env"])
            self.assertEqual(call.kwargs["env"]["KEEP"], "1")

        burst.reset_mock()
        with mock.patch.object(h, "log") as logged:
            self.assertFalse(backend.set_vrr(self.monitor(), "bogus"))
            self.assertEqual(burst.call_count, 0)  # never handed to kscreen-doctor
        self.assertIn("refusing VRR policy", logged.call_args.args[0])

    def test_holds_manual_off_is_never(self):
        holds = h.VrrHolds()
        m = self.monitor("automatic")
        self.assertEqual(holds.manual(m, True), "always")
        self.assertEqual(holds.held["DP-1"]["before"], "automatic")
        self.assertIsNone(holds.manual(self.monitor("always", vrr_on=True), True))  # already on: no write
        # The tray switch is on/off: off is Never, whatever was there before.
        self.assertEqual(holds.manual(self.monitor("always", vrr_on=True), False), "never")
        self.assertEqual(holds.held, {})
        self.assertEqual(h.VrrHolds().manual(self.monitor("always", vrr_on=True), False), "never")
        self.assertIsNone(h.VrrHolds().manual(self.monitor("never"), False))  # already off
        self.assertIsNone(h.VrrHolds().manual(self.monitor("automatic"), False))  # shown unticked: nothing to do

    def test_tray_rows(self):
        oled = Monitor("DP-1", "XG32", hdr_supported=True, vrr_supported=True, vrr_policy="always", vrr_on=True)
        lcd = Monitor("DP-2", "VG27A", hdr_supported=True, vrr_supported=True, vrr_policy="automatic")
        tv = Monitor("HDMI-A-1", "TV")

        def view(rows):
            return [r if r[0] in ("heading", "separator", "take_over") else (r[0], r[2], r[3], r[4]) for r in rows]

        self.assertEqual(view(h.tray_rows([oled, lcd, tv], True, True, set())), [
            ("heading", "XG32"), ("hdr", "HDR", False, True), ("vrr", "VRR", True, True),
            ("separator",),
            ("heading", "VG27A"), ("hdr", "HDR", False, True), ("vrr", "VRR", False, True),  # Automatic shows unticked
            ("separator",),
            ("heading", "TV"), ("hdr", "HDR (N/A)", False, False), ("vrr", "VRR (N/A)", False, False)])
        # System-managed: greyed, still showing the desktop's real state, plus one way back.
        self.assertEqual(view(h.tray_rows([oled, tv], True, False, set())), [
            ("heading", "XG32"), ("hdr", "HDR", False, True), ("vrr", "VRR (system)", True, False),
            ("separator",),
            ("heading", "TV"), ("hdr", "HDR (N/A)", False, False), ("vrr", "VRR (N/A)", False, False),
            ("take_over",)])
        self.assertEqual(view(h.tray_rows([oled], True, True, {"DP-1"}))[2], ("vrr", "VRR (paused)", True, False))
        # GNOME: no VRR rows, no take-over link.
        self.assertEqual(view(h.tray_rows([oled], False, False, set())),
                         [("heading", "XG32"), ("hdr", "HDR", False, True)])

    def test_tray_label_and_icon(self):
        # Rows are nudged right so the text sits under the monitor name.
        self.assertEqual(h.tray_label("VRR"), "\u2007\u2007\u2007VRR")
        self.assertEqual(h.tray_label("VRR (system)"), "\u2007\u2007\u2007VRR (system)")
        self.assertEqual(h.tray_label("HDR (N/A)"), "\u2007\u2007\u2007HDR (N/A)")
        # The box is drawn from this word, not an icon name: no theme has an empty box
        # (Breeze's actions/16/checkbox.svg is dialog-ok-apply, a tick), so names made both states
        # look ticked. The drawing itself needs Qt and is checked on a live tray.
        self.assertEqual(h.tray_state_icon(True), "filled")
        self.assertEqual(h.tray_state_icon(False), "empty")
        mon = Monitor("DP-1", "X", hdr_supported=True, vrr_supported=True, vrr_policy="always", vrr_on=True)
        boxes = [h.tray_state_icon(row[3]) for row in h.tray_rows([mon], True, True, set()) if row[0] in ("hdr", "vrr")]
        self.assertEqual(boxes, ["empty", "filled"])  # HDR off, VRR on: the two states differ

    def test_holds_release_and_quit(self):
        holds = h.VrrHolds()
        a, b = self.monitor(), self.monitor(name="B")
        b.id = "DP-2"
        holds.start("game.exe", [a, b])
        # Only a monitor that still reads Always is written: a policy that never landed is left alone.
        on_a, on_b = self.monitor(vrr_policy="always", vrr_on=True), self.monitor(vrr_policy="always", vrr_on=True, name="B")
        on_b.id = "DP-2"
        self.assertEqual(holds.release([a, on_b]), [(on_b, "never")])
        self.assertEqual(holds.held, {})
        self.assertEqual(holds.release([on_a]), [])  # idempotent
        holds.start("game.exe", [a])
        holds.manual(a, False)  # an explicit off ends the game hold too
        self.assertEqual(holds.held, {})

        holds = h.VrrHolds()
        holds.start("game.exe", [a])
        holds.manual(b, True)
        self.assertEqual(holds.release([on_a, on_b], keep_manual=True), [(on_a, "never")])  # quit keeps a manual on
        self.assertEqual(list(holds.held), ["DP-2"])  # the game hold is dropped, the manual one kept for next run
        self.assertEqual(holds.release([on_a, on_b], keep_manual=True), [])

    def test_holds_start_stop_restores_previous(self):
        holds = h.VrrHolds()
        a = self.monitor("automatic")
        self.assertEqual(holds.start("game.exe", [a]), [(a, "always")])
        self.assertEqual(holds.held["DP-1"], {"before": "automatic", "after": "always", "games": ["game.exe"],
                                                 "manual": False})
        self.assertEqual(holds.start("game.exe", [a]), [])  # already held by this game
        on = self.monitor("always", vrr_on=True)            # what the monitor reads after the write
        self.assertEqual(holds.stop("game.exe", [on]), [(on, "automatic")])
        self.assertEqual(holds.held, {})
        # The policy never landed, or the user changed it: the hold is dropped but nothing is written.
        holds.start("game.exe", [a])
        self.assertEqual(holds.stop("game.exe", [a]), [])
        self.assertEqual(holds.held, {})

    def test_holds_skip_monitor_already_always(self):
        # Already Always and not by us: turning it "on" records nothing, so closing writes nothing.
        held = self.monitor("always", vrr_on=True)
        holds = h.VrrHolds()
        self.assertEqual(holds.start("game.exe", [held]), [])
        self.assertEqual(holds.held, {})
        self.assertEqual(holds.stop("game.exe", [held]), [])

    def test_holds_two_games_one_monitor(self):
        holds = h.VrrHolds()
        a = self.monitor("automatic")
        on = self.monitor("always", vrr_on=True)
        holds.start("one.exe", [a])
        holds.start("two.exe", [a])
        self.assertEqual(holds.held["DP-1"]["games"], ["one.exe", "two.exe"])
        self.assertEqual(holds.stop("one.exe", [on]), [])  # the other game still needs it
        self.assertEqual(holds.held["DP-1"]["games"], ["two.exe"])
        self.assertEqual(holds.stop("two.exe", [on]), [(on, "automatic")])

    def test_holds_manual_change_mid_game_is_kept(self):
        holds = h.VrrHolds()
        a = self.monitor("automatic")
        holds.start("game.exe", [a])
        # Turned off by hand mid-game: stop() sees it off and writes nothing, so the choice stands.
        off = self.monitor("never")
        self.assertEqual(holds.stop("game.exe", [off]), [])
        self.assertEqual(holds.held, {})
        # A manual on during the game keeps the monitor held, and stop() then puts back the game's word.
        holds = h.VrrHolds()
        holds.start("game.exe", [a])
        self.assertEqual(holds.manual(a, True), "always")
        self.assertEqual(holds.stop("game.exe", [self.monitor("always", vrr_on=True)]), [])
        self.assertEqual(holds.held["DP-1"]["manual"], True)

    def test_holds_persist_and_reconcile(self):
        a, b = self.monitor("automatic", name="A"), self.monitor(vrr_policy="always", vrr_on=True, name="B")
        b.id = "DP-2"
        saved = {"DP-1": {"before": "automatic", "games": ["gone.exe"], "manual": False},
                 "DP-2": {"before": "bogus", "games": ["gone.exe", "running.exe"], "manual": False}}
        holds = h.VrrHolds(saved)
        self.assertEqual(holds.held["DP-2"]["before"], "automatic")  # clamped to a real word on load
        # DP-1's only holder is gone; DP-2's is still running, so only DP-1 comes back.
        self.assertEqual(holds.forget_games({"running.exe"}), [("DP-1", "automatic", "always")])
        self.assertEqual(holds.held["DP-2"]["games"], ["running.exe"])
        self.assertEqual(h.VrrHolds({}).forget_games(set()), [])
        # A manual "on" survives a restart even with no game running.
        manual = h.VrrHolds({"DP-1": {"before": "never", "games": [], "manual": True}})
        self.assertEqual(manual.forget_games(set()), [])
        self.assertEqual(list(manual.held), ["DP-1"])
        # A hold that never landed is forgotten without a write.
        ghost = h.VrrHolds({"DP-1": {"before": "never", "games": ["gone.exe"], "manual": False}})
        self.assertEqual(ghost.forget_games(set()), [("DP-1", "never", "always")])

    def test_vrr_inert(self):
        on, off = Game(name="G", vrr="always"), Game(name="G")
        self.assertTrue(h.vrr_inert(on, True))
        self.assertFalse(h.vrr_inert(on, False))
        self.assertFalse(h.vrr_inert(off, True))
        self.assertFalse(h.vrr_inert(off, False))

    def test_vrr_gate_is_one_rule(self):
        m = self.monitor()
        self.assertEqual(h.vrr_blocked(m, True, True, set()), "")
        self.assertIn("KDE Plasma", h.vrr_blocked(m, False, True, set()))
        self.assertIn("managed by your system", h.vrr_blocked(m, True, False, set()))
        self.assertIn("left alone this session", h.vrr_blocked(m, True, True, {"DP-1"}))
        # The desktop managing VRR is reported ahead of a blocked monitor: it is the more basic reason.
        self.assertIn("managed by your system", h.vrr_blocked(m, True, False, {"DP-1"}))
        # A different monitor is not affected by another one being blocked.
        other = self.monitor(name="B")
        other.id = "DP-2"
        self.assertEqual(h.vrr_blocked(other, True, True, {"DP-1"}), "")

    def test_config_without_vrr_keys_loads(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "config.json"
            path.write_text(json.dumps({"show_osd": False, "games": [{"name": "G", "exe": "/g.exe"}]}), encoding="utf-8")
            with mock.patch.object(h.Config, "path", staticmethod(lambda: path)):
                loaded = h.Config.load()
        self.assertFalse(loaded.show_osd)
        self.assertTrue(loaded.vrr_system_managed)  # a config written before VRR existed still loads
        self.assertEqual(loaded.vrr_held, {})
        self.assertFalse(loaded.vrr_ours)
        self.assertEqual([g.vrr for g in loaded.games], [""])
        self.assertFalse(h.Game(name="G").vrr)

    def test_games_can_ask_for_never(self):
        # Off while playing: the mirror image of Always, held and put back the same way.
        holds = h.VrrHolds()
        a = self.monitor("automatic")
        self.assertEqual(holds.start("game.exe", [a], "never"), [(a, "never")])
        self.assertEqual(holds.held["DP-1"]["after"], "never")
        off = self.monitor("never")
        self.assertEqual(holds.stop("game.exe", [off]), [(off, "automatic")])
        # Already Never without us: nothing written, nothing recorded.
        self.assertEqual(holds.start("game.exe", [off], "never"), [])
        self.assertEqual(holds.held, {})

    def test_game_vrr_values_survive_a_config_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "config.json"
            cfg = h.Config()
            cfg.games = [h.Game(name="A", vrr="never"), h.Game(name="B", vrr="always"), h.Game(name="C")]
            with mock.patch.object(h.Config, "path", staticmethod(lambda: path)):
                cfg.save()
                loaded = h.Config.load()
        self.assertEqual([g.vrr for g in loaded.games], ["never", "always", ""])

    def test_old_boolean_vrr_flag_migrates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "config.json"
            path.write_text(json.dumps({"games": [{"name": "was on", "vrr": True}, {"name": "was off", "vrr": False},
                                                {"name": "bogus", "vrr": "sometimes"}]}), encoding="utf-8")
            with mock.patch.object(h.Config, "path", staticmethod(lambda: path)):
                loaded = h.Config.load()
        self.assertEqual([g.vrr for g in loaded.games], ["always", "", ""])

    def test_vrr_summary(self):
        self.assertEqual(h.vrr_summary(h.Game(vrr="always")), "On")
        self.assertEqual(h.vrr_summary(h.Game(vrr="never")), "Off")
        self.assertEqual(h.vrr_summary(h.Game()), "No change")

    def test_holds_from_before_never_existed_put_always_back(self):
        holds = h.VrrHolds({"DP-1": {"before": "automatic", "games": ["game.exe"], "manual": False}})
        self.assertEqual(holds.held["DP-1"]["after"], "always")
        on = self.monitor("always", vrr_on=True)
        self.assertEqual(holds.stop("game.exe", [on]), [(on, "automatic")])



if __name__ == "__main__":
    unittest.main()
