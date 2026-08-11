"""Test di verifica per DXRotator.  Eseguire:  python -m unittest discover -s tests"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dxrotator import geo, dxcc, rotor, sources, engine, bands          # noqa: E402
from dxrotator.config import AppConfig                            # noqa: E402
from tools import send_test                                       # noqa: E402


# --------------------------------------------------------------------------
class TestGeo(unittest.TestCase):

    def test_locator_valid(self):
        for good in ("JN61", "JN61fu", "PM95", "RE78ix", "AA00aa00"):
            self.assertTrue(geo.is_valid_locator(good), good)
        for bad in ("", "J61", "ZZ99", "JN6", "JN611", "1N61"):
            self.assertFalse(geo.is_valid_locator(bad), bad)

    def test_locator_known_points(self):
        lat, lon = geo.locator_to_latlon("JN61fu")     # Roma
        self.assertAlmostEqual(lat, 41.90, delta=0.1)
        self.assertAlmostEqual(lon, 12.54, delta=0.1)

        lat, lon = geo.locator_to_latlon("PM95")       # Tokyo
        self.assertAlmostEqual(lat, 35.5, delta=0.6)
        self.assertAlmostEqual(lon, 139.0, delta=1.1)

    def test_locator_roundtrip(self):
        for loc in ("JN61fu", "PM95tq", "FN31pr", "QF22lb", "GF05tj"):
            lat, lon = geo.locator_to_latlon(loc)
            self.assertEqual(geo.latlon_to_locator(lat, lon, 6).upper(), loc.upper())

    def test_bearing_reference(self):
        # Roma -> Tokyo, valore noto ~ 43 gradi, ~9870 km
        b = geo.bearing_between_locators("JN61fu", "PM95tq")
        self.assertAlmostEqual(b.short_path, 43.0, delta=3.0)
        self.assertAlmostEqual(b.distance_km, 9870.0, delta=120.0)
        self.assertAlmostEqual(b.long_path, geo.normalize_deg(b.short_path + 180), places=6)

        # Roma -> New York ~ 300 gradi, ~6900 km
        b = geo.bearing_between_locators("JN61fu", "FN30as")
        self.assertAlmostEqual(b.short_path, 300.0, delta=4.0)
        self.assertAlmostEqual(b.distance_km, 6900.0, delta=200.0)

        # Roma -> Sydney ~ 90 gradi
        b = geo.bearing_between_locators("JN61fu", "QF56od")
        self.assertAlmostEqual(b.short_path, 90.0, delta=8.0)

    def test_bearing_cardinal(self):
        # dallo stesso meridiano verso nord
        b = geo.great_circle(0.0, 0.0, 10.0, 0.0)
        self.assertAlmostEqual(b.short_path, 0.0, delta=0.01)
        b = geo.great_circle(0.0, 0.0, 0.0, 10.0)
        self.assertAlmostEqual(b.short_path, 90.0, delta=0.01)
        b = geo.great_circle(0.0, 0.0, -10.0, 0.0)
        self.assertAlmostEqual(b.short_path, 180.0, delta=0.01)
        b = geo.great_circle(0.0, 0.0, 0.0, -10.0)
        self.assertAlmostEqual(b.short_path, 270.0, delta=0.01)

    def test_angular_difference(self):
        self.assertAlmostEqual(geo.angular_difference(350, 10), 20.0)
        self.assertAlmostEqual(geo.angular_difference(10, 350), -20.0)
        self.assertAlmostEqual(geo.angular_distance(0, 200), 160.0)
        self.assertAlmostEqual(geo.angular_distance(90, 91), 1.0)

    def test_parse_coordinate(self):
        self.assertAlmostEqual(geo.parse_coordinate("41.9"), 41.9)
        self.assertAlmostEqual(geo.parse_coordinate("41 54 N"), 41.9, places=3)
        self.assertAlmostEqual(geo.parse_coordinate("9 09 W"), -9.15, places=3)
        self.assertIsNone(geo.parse_coordinate("abc"))


# --------------------------------------------------------------------------
class TestDxcc(unittest.TestCase):

    def setUp(self):
        self.r = dxcc.DxccResolver()

    def test_effective_call(self):
        cases = {
            "IK0ABC/P": "IK0ABC",
            "IK0ABC": "IK0ABC",
            "KH6/DL1XYZ": "KH6",
            "VP2E/K1ABC": "VP2E",
            "F/IK0ABC/M": "F",
            "IK0ABC/3": "IK3ABC",
            "W1AW/4": "W4AW",
        }
        for src, want in cases.items():
            self.assertEqual(dxcc.effective_call(src), want, src)

    def test_lookup(self):
        cases = {
            "IK0ABC": "Italy",
            "IS0ABC": "Sardinia",
            "IT9ABC": "Sicily",
            "W1AW": "United States",
            "KH6XYZ": "Hawaii",
            "KL7AA": "Alaska",
            "VK3ABC": "Australia",
            "JA1XYZ": "Japan",
            "ZS6ABC": "South Africa",
            "LU1ABC": "Argentina",
            "PY2ABC": "Brazil",
            "VE3ABC": "Canada",
            "EA8ABC": "Canary Islands",
            "9A1AAA": "Croatia",
            "UA9ABC": "Asiatic Russia",
            "UA3ABC": "European Russia",
            "T77ABC": "San Marino",
            "ZL2ABC": "New Zealand",
            "VP8ABC": "Falkland Islands",
            "3D2AB": "Fiji",
            "9M6XYZ": "East Malaysia",
            "9M2XYZ": "West Malaysia",
        }
        for call, want in cases.items():
            ent = self.r.lookup(call)
            self.assertIsNotNone(ent, call)
            self.assertEqual(ent.name, want, f"{call} -> {ent.name}")

    def test_coordinates_sane(self):
        for call in ("VK3ABC", "JA1XYZ", "W1AW", "ZS6ABC"):
            ent = self.r.lookup(call)
            self.assertTrue(-90 <= ent.lat <= 90)
            self.assertTrue(-180 <= ent.lon <= 180)

    def test_hemispheres(self):
        # controlla che il segno delle longitudini sia corretto (Est positivo)
        self.assertGreater(self.r.lookup("JA1XYZ").lon, 100)     # Giappone: Est
        self.assertLess(self.r.lookup("W1AW").lon, -50)          # USA: Ovest
        self.assertLess(self.r.lookup("ZS6ABC").lat, 0)          # Sudafrica: Sud

    def test_cty_parser(self):
        sample = (
            "Sardinia:                 15:  33:  EU:   40.10:    -9.00:"
            "    -1.0:  IS0:\n"
            "    IM0,IS0,IW0U,IW0T;\n"
            "United States:            05:  08:  NA:   37.53:    91.67:"
            "     5.0:  K:\n"
            "    AA,AB,K,N,W,=W1AW<41.71/72.73>;\n"
        )
        pfx, exact = dxcc.parse_cty_dat(sample)
        self.assertIn("IS0", pfx)
        self.assertEqual(pfx["IS0"].name, "Sardinia")
        # cty.dat ha la longitudine positiva a Ovest: -9.00 -> +9.00 Est
        self.assertAlmostEqual(pfx["IS0"].lon, 9.00, places=2)
        self.assertAlmostEqual(pfx["K"].lon, -91.67, places=2)
        self.assertIn("W1AW", exact)
        self.assertAlmostEqual(exact["W1AW"].lat, 41.71, places=2)
        self.assertAlmostEqual(exact["W1AW"].lon, -72.73, places=2)


# --------------------------------------------------------------------------
class TestRotorGeometry(unittest.TestCase):

    def test_north_centered(self):
        # fermo a 180 (Nord centrato): il percorso breve attraverso Nord e' libero
        cfg = rotor.RotorConfig(range_start=180.0, range_span=360.0)
        self.assertAlmostEqual(rotor.bearing_to_rotor(180.0, cfg), 0.0)
        self.assertAlmostEqual(rotor.bearing_to_rotor(0.0, cfg), 180.0)
        u10 = rotor.bearing_to_rotor(10.0, cfg)
        u350 = rotor.bearing_to_rotor(350.0, cfg)
        self.assertAlmostEqual(abs(u10 - u350), 20.0)      # passa da Nord

    def test_south_centered(self):
        # fermo a 0 (Sud centrato): da 10 a 350 si deve fare il giro lungo
        cfg = rotor.RotorConfig(range_start=0.0, range_span=360.0)
        u10 = rotor.bearing_to_rotor(10.0, cfg)
        u350 = rotor.bearing_to_rotor(350.0, cfg)
        self.assertAlmostEqual(abs(u10 - u350), 340.0)

    def test_overlap_450(self):
        cfg = rotor.RotorConfig(range_start=180.0, range_span=450.0)
        near_low = rotor.bearing_to_rotor(200.0, cfg, near=20.0)
        near_high = rotor.bearing_to_rotor(200.0, cfg, near=400.0)
        self.assertAlmostEqual(near_low, 20.0)
        self.assertAlmostEqual(near_high, 380.0)

    def test_stop_bearing_reachable_from_both_sides(self):
        # fermo a Nord, escursione 360: l'azimut 0 e' sia inizio sia fine corsa.
        # Stando a 350 si deve arrivare a Nord con 10 gradi, non con 350.
        cfg = rotor.RotorConfig(range_start=0.0, range_span=360.0,
                                safety_margin=0.0)
        u350 = rotor.bearing_to_rotor(350.0, cfg)
        self.assertAlmostEqual(u350, 350.0)
        self.assertAlmostEqual(rotor.bearing_to_rotor(0.0, cfg, near=u350), 360.0)
        # partendo dal lato opposto resta la soluzione a inizio corsa
        self.assertAlmostEqual(rotor.bearing_to_rotor(0.0, cfg, near=10.0), 0.0)

        c = rotor.Dcu1Controller(cfg, transport=rotor.SimulatedTransport())
        c.connect()
        c.set_current_bearing(350.0)
        self.assertAlmostEqual(c.travel_to(0.0), 10.0, delta=0.01)
        c.set_current_bearing(10.0)
        self.assertAlmostEqual(c.travel_to(0.0), 10.0, delta=0.01)

    def test_safety_margin_clamps(self):
        # impianto reale: fermo a 335 gradi veri, margine 10
        cfg = rotor.RotorConfig(range_start=335.0, range_span=360.0,
                                safety_margin=10.0, speed_deg_s=6.0)
        c = rotor.Dcu1Controller(cfg, transport=rotor.SimulatedTransport())
        c.connect()

        # 0 gradi -> u=25, ben dentro la corsa: nessuna limitazione
        c.set_current_bearing(0.0)
        self.assertTrue(c.goto(90.0))
        self.assertEqual(c.transport.sent[-1], "AP1090;AM1;")

        # 335 = il fermo stesso: deve essere limitato al bordo piu' vicino
        c.set_current_bearing(0.0)          # u = 25, vicino a inizio corsa
        self.assertTrue(c.goto(335.0))
        self.assertEqual(c.transport.sent[-1], "AP1345;AM1;")
        self.assertAlmostEqual(c.reachable_bearing(335.0), 345.0, delta=0.01)

        # arrivando dall'altro lato si limita al bordo opposto
        c.set_current_bearing(300.0)        # u = 325, vicino a fine corsa
        self.assertTrue(c.goto(335.0))
        self.assertEqual(c.transport.sent[-1], "AP1325;AM1;")

        # 340 cade dentro il margine -> limitato a 345
        c.set_current_bearing(0.0)
        c.goto(340.0)
        self.assertEqual(c.transport.sent[-1], "AP1345;AM1;")

        # 350 e' fuori dal margine -> passa intatto
        c.set_current_bearing(0.0)
        c.goto(350.0)
        self.assertEqual(c.transport.sent[-1], "AP1350;AM1;")

    def test_blind_sector(self):
        cfg = rotor.RotorConfig(range_start=335.0, range_span=360.0,
                                safety_margin=10.0)
        a, b = rotor.blind_sector(cfg)
        self.assertAlmostEqual(a, 325.0, delta=0.01)
        self.assertAlmostEqual(b, 345.0, delta=0.01)
        self.assertIsNone(rotor.blind_sector(
            rotor.RotorConfig(safety_margin=0.0)))

    def test_margin_never_blocks_everything(self):
        # margine assurdo rispetto alla corsa: viene ignorato
        cfg = rotor.RotorConfig(range_start=0.0, range_span=180.0,
                                safety_margin=120.0)
        u, clamped = rotor.clamp_rotor(90.0, cfg)
        self.assertFalse(clamped)
        self.assertAlmostEqual(u, 90.0)

    def test_out_of_range(self):
        cfg = rotor.RotorConfig(range_start=0.0, range_span=180.0)
        self.assertIsNone(rotor.bearing_to_rotor(270.0, cfg))
        self.assertIsNotNone(rotor.bearing_to_rotor(90.0, cfg))


class TestDcu1(unittest.TestCase):

    def _ctrl(self, **kw):
        cfg = rotor.RotorConfig(**kw)
        t = rotor.SimulatedTransport()
        c = rotor.Dcu1Controller(cfg, transport=t)
        c.connect()
        return c, t

    def test_command_format(self):
        c, t = self._ctrl()
        c.set_current_bearing(0.0)
        self.assertTrue(c.goto(135.0))
        self.assertEqual(t.sent[-1], "AP1135;AM1;")

        c.goto(7.0)
        self.assertEqual(t.sent[-1], "AP1007;AM1;")

        c.stop()
        self.assertEqual(t.sent[-1], ";")

    def test_command_split(self):
        c, t = self._ctrl(send_move_with_target=False, command_gap=0.0)
        c.set_current_bearing(0.0)
        c.goto(90.0)
        self.assertEqual(t.sent[-2:], ["AP1090;", "AM1;"])

    def test_command_gap_is_applied(self):
        import time as _t
        c, t = self._ctrl(send_move_with_target=False, command_gap=0.2)
        c.set_current_bearing(0.0)
        t0 = _t.monotonic()
        c.goto(90.0)
        elapsed = _t.monotonic() - t0
        self.assertEqual(t.sent[-2:], ["AP1090;", "AM1;"])
        self.assertGreaterEqual(elapsed, 0.19)

    def test_offset_negative(self):
        # compensazione dell'errore sistematico misurato sul DCU-1 reale
        c, t = self._ctrl(offset=-4.0)
        c.set_current_bearing(0.0)
        c.goto(300.0)
        self.assertEqual(t.sent[-1], "AP1296;AM1;")
        c.set_current_bearing(0.0)
        c.goto(2.0)                     # deve avvolgersi su 358, non su -2
        self.assertEqual(t.sent[-1], "AP1358;AM1;")

    def test_offset_applied(self):
        c, t = self._ctrl(offset=5.0)
        c.set_current_bearing(0.0)
        c.goto(100.0)
        self.assertEqual(t.sent[-1], "AP1105;AM1;")

    def _moving(self, c):
        """Mette il controller in movimento verso un target lontano."""
        c.goto(c.current_bearing + 120.0, force=True)
        self.assertTrue(c.state.moving)
        return c

    def test_stop_command_only(self):
        c, t = self._ctrl(stop_strategy="command", stop_repeat=1)
        c.stop(blocking=True)
        self.assertEqual(t.sent[-1], ";")

    def test_stop_target_only_never_sends_am1(self):
        c, t = self._ctrl(stop_strategy="target_only", stop_repeat=1,
                          speed_deg_s=0.0001)
        c.set_current_bearing(214.0)
        self._moving(c)
        t.sent.clear()
        c.stop(blocking=True)
        self.assertEqual(t.sent, ["AP1214;"])
        self.assertFalse(any("AM1" in s for s in t.sent))

    def test_stop_sends_am1_only_when_moving(self):
        # in movimento: AP1 + AM1
        c, t = self._ctrl(stop_strategy="goto_current", stop_repeat=1,
                          command_gap=0.0, speed_deg_s=0.0001)
        c.set_current_bearing(100.0)
        self._moving(c)
        t.sent.clear()
        c.stop(blocking=True)
        self.assertIn("AM1;", t.sent)

        # gia' fermo: nessun AM1, cosi' il freno non viene sbloccato per nulla
        t.sent.clear()
        self.assertFalse(c.state.moving)
        c.stop(blocking=True)
        self.assertTrue(t.sent)
        self.assertFalse(any("AM1" in s for s in t.sent),
                         f"AM1 inviato a rotore fermo: {t.sent}")

    def test_stop_repeats(self):
        c, t = self._ctrl(stop_strategy="command", stop_repeat=3,
                          stop_repeat_gap=0.05)
        c.stop(blocking=True)
        self.assertEqual(t.sent.count(";"), 3)

    def test_stop_both_order(self):
        c, t = self._ctrl(stop_strategy="both", command_gap=0.0,
                          stop_repeat=1, speed_deg_s=0.0001)
        c.set_current_bearing(90.0)
        self._moving(c)
        t.sent.clear()
        c.stop(blocking=True)
        self.assertEqual(t.sent, [";", "AP1090;", "AM1;"])

    def test_stop_is_non_blocking_by_default(self):
        import time as _t
        c, _t2 = self._ctrl(stop_strategy="command", stop_repeat=4,
                            stop_repeat_gap=0.3)
        t0 = _t.monotonic()
        c.stop()                       # deve tornare subito
        self.assertLess(_t.monotonic() - t0, 0.15)
        self.assertFalse(c.state.moving)

    def test_stop_clears_target(self):
        c, _ = self._ctrl(stop_strategy="goto_current", speed_deg_s=1.0)
        c.set_current_bearing(0.0)
        c.goto(180.0)
        self.assertTrue(c.state.moving)
        c.stop()
        self.assertFalse(c.state.moving)
        self.assertIsNone(c.state.target)
        before = c.current_bearing
        c.tick()
        self.assertAlmostEqual(c.current_bearing, before, delta=0.01)

    def test_send_raw(self):
        c, t = self._ctrl()
        c.send_raw("AS1;")
        self.assertEqual(t.sent[-1], "AS1;")
        c.send_raw(";\\r")
        self.assertEqual(t.sent[-1], ";\r")

    def test_min_move(self):
        c, t = self._ctrl(min_move=10.0)
        c.set_current_bearing(100.0)
        before = len(t.sent)
        self.assertFalse(c.goto(105.0))          # sotto la soglia meccanica
        self.assertEqual(len(t.sent), before)
        self.assertTrue(c.goto(105.0, force=True))

    def test_dead_reckoning(self):
        import time as _t
        c, _ = self._ctrl(speed_deg_s=100.0)
        c.set_current_bearing(0.0)
        c.goto(50.0)
        self.assertTrue(c.state.moving)
        _t.sleep(0.15)
        c.tick()
        self.assertGreater(c.current_bearing, 0.0)
        _t.sleep(0.6)
        c.tick()
        self.assertAlmostEqual(c.current_bearing, 50.0, delta=0.5)
        self.assertFalse(c.state.moving)

    def test_travel_and_eta(self):
        c, _ = self._ctrl(range_start=0.0, range_span=360.0, speed_deg_s=6.0)
        c.set_current_bearing(10.0)
        self.assertAlmostEqual(c.travel_to(350.0), 340.0, delta=0.1)
        self.assertAlmostEqual(c.eta_seconds(350.0), 340.0 / 6.0, delta=0.1)


# --------------------------------------------------------------------------
class TestReadback(unittest.TestCase):

    def test_parse_response(self):
        self.assertAlmostEqual(rotor.parse_ai1_response(b";123\r"), 123.0)
        self.assertAlmostEqual(rotor.parse_ai1_response(b"045"), 45.0)
        self.assertAlmostEqual(rotor.parse_ai1_response(b";007\r\n"), 7.0)
        self.assertAlmostEqual(rotor.parse_ai1_response(b";360"), 0.0)
        self.assertIsNone(rotor.parse_ai1_response(b""))
        self.assertIsNone(rotor.parse_ai1_response(b";---"))

    def test_query_without_answer(self):
        # controller muto (cavo con solo TX): nessuna risposta, niente crash
        t = rotor.SimulatedTransport(answer_ai1=False)
        c = rotor.Dcu1Controller(rotor.RotorConfig(read_timeout=0.1), transport=t)
        c.connect()
        self.assertIsNone(c.query_position())
        self.assertGreaterEqual(c.state.read_failures, 1)
        self.assertFalse(c.state.reading)

    def test_query_with_answer(self):
        t = rotor.SimulatedTransport(answer_ai1=True, start=123.0)
        c = rotor.Dcu1Controller(rotor.RotorConfig(read_timeout=0.5), transport=t)
        c.connect()
        self.assertAlmostEqual(c.query_position(), 123.0, delta=1.0)
        self.assertIn("123", c.state.last_raw_response)

    def test_polling_tracks_controller(self):
        import time as _t
        # il simulatore introduce un errore di scala del 3%, come l'impianto reale
        t = rotor.SimulatedTransport(answer_ai1=True, start=0.0, speed=1000.0,
                                     scale_error=0.03)
        cfg = rotor.RotorConfig(range_start=0.0, range_span=360.0,
                                safety_margin=0.0, read_position=True,
                                poll_interval=0.2, read_timeout=0.5)
        c = rotor.Dcu1Controller(cfg, transport=t)
        c.connect()
        c.goto(100.0, force=True)
        deadline = _t.monotonic() + 3.0
        while _t.monotonic() < deadline and not c.state.reading:
            _t.sleep(0.05)
        _t.sleep(0.6)
        # il controller si ferma a 103 per l'errore di scala: il programma
        # deve mostrare 103, non il 100 comandato
        self.assertTrue(c.state.reading)
        self.assertAlmostEqual(c.current_bearing, 103.0, delta=1.5)
        c.tick()
        self.assertAlmostEqual(c.current_bearing, 103.0, delta=1.5)
        c.disconnect()

    def test_margin_protection_stops(self):
        import time as _t
        t = rotor.SimulatedTransport(answer_ai1=True, start=350.0, speed=1000.0)
        cfg = rotor.RotorConfig(range_start=335.0, range_span=360.0,
                                safety_margin=10.0, read_position=True,
                                poll_interval=0.15, read_timeout=0.5,
                                stop_on_margin=True)
        c = rotor.Dcu1Controller(cfg, transport=t)
        c.connect()
        c.state.moving = True
        deadline = _t.monotonic() + 3.0
        while _t.monotonic() < deadline and c.state.moving:
            _t.sleep(0.05)
        # 350 e' dentro il margine 325..345? no: u(350)=15 -> dentro [10,350]
        # forziamo il caso reale portando il simulatore a 340 (u=5)
        c.disconnect()

        t2 = rotor.SimulatedTransport(answer_ai1=True, start=340.0, speed=1000.0)
        c2 = rotor.Dcu1Controller(cfg, transport=t2)
        c2.connect()
        c2.state.moving = True
        deadline = _t.monotonic() + 3.0
        while _t.monotonic() < deadline and c2.state.moving:
            _t.sleep(0.05)
        self.assertFalse(c2.state.moving)
        self.assertTrue(any("margine di sicurezza" in h
                            for h in c2.state.history))
        c2.disconnect()


class TestSources(unittest.TestCase):

    def test_wsjtx_status(self):
        pkt = send_test.wsjtx_status("VK3ABC", "QF22", de_call="IK0TEST",
                                     de_grid="JN61fu")
        t = sources.WsjtxDecoder().decode(pkt)
        self.assertIsNotNone(t)
        self.assertEqual(t.call, "VK3ABC")
        self.assertEqual(t.grid, "QF22")
        self.assertEqual(t.kind, "status")
        self.assertEqual(t.frequency_hz, 14074000)

    def test_wsjtx_status_no_grid(self):
        pkt = send_test.wsjtx_status("VK3ABC", "")
        t = sources.WsjtxDecoder().decode(pkt)
        self.assertEqual(t.call, "VK3ABC")
        self.assertEqual(t.grid, "")

    def test_wsjtx_decode(self):
        d = sources.WsjtxDecoder()
        t = d.decode(send_test.wsjtx_decode("CQ VK3ABC QF22"))
        self.assertEqual(t.call, "VK3ABC")
        self.assertEqual(t.grid, "QF22")

        d.my_call = "IK0TEST"
        t = d.decode(send_test.wsjtx_decode("IK0TEST JA1XYZ PM95"))
        self.assertEqual(t.call, "JA1XYZ")
        self.assertEqual(t.grid, "PM95")

        t = d.decode(send_test.wsjtx_decode("IK0TEST JA1XYZ RR73"))
        self.assertEqual(t.call, "JA1XYZ")
        self.assertEqual(t.grid, "")

        t = d.decode(send_test.wsjtx_decode("CQ DX W6ABC DM03"))
        self.assertEqual(t.call, "W6ABC")
        self.assertEqual(t.grid, "DM03")

    def test_bad_packet(self):
        self.assertIsNone(sources.WsjtxDecoder().decode(b"garbage"))
        self.assertIsNone(sources.WsjtxDecoder().decode(b""))

    def test_n1mm_contact(self):
        t = sources.N1mmDecoder().decode(send_test.n1mm_contact("ZL2ABC", "RE78"))
        self.assertEqual(t.call, "ZL2ABC")
        self.assertEqual(t.grid, "RE78")
        self.assertEqual(t.source, "N1MM")

    def test_n1mm_rotor(self):
        t = sources.N1mmDecoder().decode(send_test.n1mm_rotor(275.5))
        self.assertAlmostEqual(t.azimuth, 275.5)
        self.assertEqual(t.kind, "rotor")

    def test_looks_like_grid(self):
        self.assertTrue(sources.looks_like_grid("JN61"))
        self.assertTrue(sources.looks_like_grid("jn61fu"))
        self.assertFalse(sources.looks_like_grid("RR73"))
        self.assertFalse(sources.looks_like_grid("-12"))
        self.assertFalse(sources.looks_like_grid("IK0ABC"))


# --------------------------------------------------------------------------
class TestEngine(unittest.TestCase):

    def _engine(self, **over):
        cfg = AppConfig()
        cfg.my_locator = "JN61fu"
        cfg.auto_rotate = True
        cfg.auto_threshold = 30.0
        cfg.auto_hold_seconds = 0.0
        for k, v in over.items():
            setattr(cfg, k, v)
        ctrl = rotor.Dcu1Controller(rotor.RotorConfig(speed_deg_s=1e6),
                                    transport=rotor.SimulatedTransport())
        ctrl.connect()
        return engine.RotatorEngine(cfg, controller=ctrl), ctrl

    def test_grid_preferred_over_dxcc(self):
        eng, _ = self._engine()
        sol = eng.solve(sources.DxTarget(call="VK3ABC", grid="QF22"))
        self.assertEqual(sol.precision, "locatore")
        sol2 = eng.solve(sources.DxTarget(call="VK3ABC"))
        self.assertEqual(sol2.precision, "dxcc")
        # entrambi puntano verso l'Australia, ma non allo stesso punto
        self.assertLess(geo.angular_distance(sol.azimuth, sol2.azimuth), 40)

    def test_direct_azimuth(self):
        eng, _ = self._engine()
        sol = eng.solve(sources.DxTarget(azimuth=275.0, source="N1MM", kind="rotor"))
        self.assertEqual(sol.precision, "diretto")
        self.assertAlmostEqual(sol.azimuth, 275.0)

    def test_long_path(self):
        eng, _ = self._engine(long_path=True)
        sol = eng.solve(sources.DxTarget(call="VK3ABC", grid="QF22"))
        self.assertAlmostEqual(sol.azimuth,
                               geo.normalize_deg(sol.short_path + 180), places=5)

    def test_threshold_blocks_small_moves(self):
        eng, ctrl = self._engine(auto_threshold=30.0)
        ctrl.set_current_bearing(100.0)
        ok, why = eng.should_rotate(120.0)      # differenza 20 gradi
        self.assertFalse(ok)
        self.assertIn("soglia", why)
        ok, why = eng.should_rotate(140.0)      # differenza 40 gradi
        self.assertTrue(ok)

    def test_threshold_wraps_around_north(self):
        eng, ctrl = self._engine(auto_threshold=30.0)
        ctrl.set_current_bearing(350.0)
        self.assertFalse(eng.should_rotate(10.0)[0])    # 20 gradi reali
        self.assertTrue(eng.should_rotate(50.0)[0])     # 60 gradi reali

    def test_auto_disabled(self):
        eng, ctrl = self._engine(auto_rotate=False)
        ctrl.set_current_bearing(0.0)
        ok, why = eng.should_rotate(180.0)
        self.assertFalse(ok)
        self.assertIn("disattivato", why)

    def test_handle_target_sends_command(self):
        eng, ctrl = self._engine()
        ctrl.set_current_bearing(0.0)
        t = sources.DxTarget(call="VK3ABC", grid="QF22", source="WSJT-X",
                             kind="status")
        sol, sent, why = eng.handle_target(t)
        self.assertTrue(sent, why)
        self.assertTrue(ctrl.transport.sent[-1].startswith("AP1"))
        # il rotore raggiunge la posizione: un secondo target identico
        # non deve generare alcun comando
        import time as _t
        _t.sleep(0.05)
        ctrl.tick()
        self.assertFalse(ctrl.state.moving)
        sol2, sent2, why2 = eng.handle_target(t)
        self.assertFalse(sent2)

    def test_source_filter(self):
        eng, ctrl = self._engine()
        eng.cfg.auto_sources["wsjtx_decode"] = False
        ctrl.set_current_bearing(0.0)
        t = sources.DxTarget(call="VK3ABC", grid="QF22", source="WSJT-X",
                             kind="decode")
        _sol, sent, why = eng.handle_target(t)
        self.assertFalse(sent)
        self.assertIn("non abilitata", why)

    def test_no_home_position(self):
        eng, _ = self._engine(my_locator="", use_latlon=False)
        self.assertIsNone(eng.solve(sources.DxTarget(call="VK3ABC")))


# --------------------------------------------------------------------------
class TestBands(unittest.TestCase):

    def test_band_for_frequency(self):
        cases = {
            14074000: "20m", 14350000: "20m",
            18100000: "17m", 21074000: "15m", 24915000: "12m",
            28074000: "10m", 50313000: "6m",
            7074000: "40m", 3573000: "80m", 1840000: "160m",
            10136000: "30m", 5357000: "60m",
            144174000: "2m", 432000000: "70cm",
        }
        for hz, want in cases.items():
            self.assertEqual(bands.band_for_frequency(hz), want, hz)

    def test_band_unknown(self):
        for bad in (0, None, "", 9000000, 200000000, "abc"):
            self.assertIsNone(bands.band_for_frequency(bad), bad)

    def test_is_enabled(self):
        only_beam = bands.default_enabled_bands(bands.DIRECTIVE_BANDS)
        self.assertTrue(bands.is_enabled("20m", only_beam))
        self.assertTrue(bands.is_enabled("6m", only_beam))
        self.assertFalse(bands.is_enabled("40m", only_beam))
        self.assertFalse(bands.is_enabled("160m", only_beam))
        # banda sconosciuta: ammessa
        self.assertTrue(bands.is_enabled(None, only_beam))

    def test_engine_blocks_vertical_bands(self):
        cfg = AppConfig()
        cfg.my_locator = "JN61fu"
        cfg.auto_rotate = True
        cfg.auto_hold_seconds = 0.0
        cfg.enabled_bands = bands.default_enabled_bands(bands.DIRECTIVE_BANDS)
        ctrl = rotor.Dcu1Controller(rotor.RotorConfig(speed_deg_s=1e6),
                                    transport=rotor.SimulatedTransport())
        ctrl.connect()
        eng = engine.RotatorEngine(cfg, controller=ctrl)
        ctrl.set_current_bearing(0.0)

        # 20 metri: hexbeam sul rotatore -> ruota
        t = sources.DxTarget(call="VK3ABC", grid="QF22", source="WSJT-X",
                             kind="status", frequency_hz=14074000)
        _sol, sent, _why = eng.handle_target(t)
        self.assertTrue(sent)

        # 40 metri: verticale fissa -> nessun comando
        ctrl.transport.sent.clear()
        ctrl.set_current_bearing(0.0)
        t40 = sources.DxTarget(call="JA1XYZ", grid="PM95", source="WSJT-X",
                               kind="status", frequency_hz=7074000)
        sol, sent, why = eng.handle_target(t40)
        self.assertFalse(sent)
        self.assertIsNone(sol)
        self.assertIn("40m", why)
        self.assertEqual(ctrl.transport.sent, [])

    def test_decode_inherits_frequency_from_status(self):
        d = sources.WsjtxDecoder()
        self.assertEqual(d.decode(send_test.wsjtx_decode("CQ VK3ABC QF22")
                                  ).frequency_hz, 0)
        d.decode(send_test.wsjtx_status("W1AW", "FN31", freq=7074000))
        t = d.decode(send_test.wsjtx_decode("CQ VK3ABC QF22"))
        self.assertEqual(t.frequency_hz, 7074000)


class TestClearedStation(unittest.TestCase):

    def test_status_without_dx_call_is_a_clear_event(self):
        d = sources.WsjtxDecoder()
        t = d.decode(send_test.wsjtx_status("", ""))
        self.assertIsNotNone(t)
        self.assertTrue(t.cleared)
        self.assertFalse(t.is_empty)      # deve arrivare alla GUI
        self.assertEqual(t.kind, "status")

    def test_normal_status_is_not_a_clear(self):
        d = sources.WsjtxDecoder()
        t = d.decode(send_test.wsjtx_status("VK3ABC", "QF22"))
        self.assertFalse(t.cleared)

    def test_frequency_kept_on_clear(self):
        d = sources.WsjtxDecoder()
        t = d.decode(send_test.wsjtx_status("", "", freq=14074000))
        self.assertEqual(t.frequency_hz, 14074000)


class TestConfig(unittest.TestCase):

    def test_roundtrip(self):
        import json
        import tempfile
        cfg = AppConfig()
        cfg.my_locator = "JN61fu"
        cfg.auto_threshold = 45.0
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.json")
            cfg.save(p)
            back = AppConfig.load(p)
            self.assertEqual(back.my_locator, "JN61fu")
            self.assertEqual(back.auto_threshold, 45.0)
            self.assertIn("wsjtx_status", back.auto_sources)
            with open(p) as fh:
                json.load(fh)

    def test_unknown_keys_ignored(self):
        cfg = AppConfig.from_dict({"my_locator": "AA00", "chiave_ignota": 1})
        self.assertEqual(cfg.my_locator, "AA00")


if __name__ == "__main__":
    unittest.main(verbosity=2)
