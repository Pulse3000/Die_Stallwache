"""
Vertragstests — Erkennungsvertrag v1 (docs/erkennungsvertrag.md).

Diese Tests sind der Vertrag. Nicht löschen, nicht überspringen, nicht
abschwächen, keine Schwellen anpassen, um grün zu werden. Erlaubt ist nur,
bei der Plan-Freigabe die Import-Zeile auf den finalen Paketpfad zu ändern.

Wo ein Wert Beschlusssache ist (B15 Keypoint-Namen, B16 Dominanz-Anteil,
B17 Eskalations-Typ), prüfen die Tests das Verhalten relativ zur Konfig,
nicht den Wert. Aktive Werte (0.80, 30 min, 60 min) sind festgenagelt.
"""

import math
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from erkennung import (  # noqa: E402  (Import-Pfad bei Plan-Freigabe anpassbar)
    API_TYPEN_BASIS,
    Austreibungswaechter,
    Ereignis,
    Frame,
    Konfig,
    Objekt,
    Sperre,
    api_nutzlast,
    faehigkeitspruefung,
    keypoints_aus_array,
    winkel_aus_objekt,
)

T0 = 1_800_000_000.0
KAMERA = "stallwache"
KUH_BOX = (100.0, 100.0, 500.0, 400.0)


def kuh(track=7, box=KUH_BOX, keypoints=None, klasse="kuh"):
    return Objekt(klasse, 0.9, box, keypoints or {}, track_id=track)


def blase(konf=0.9, box=(480.0, 200.0, 540.0, 260.0), klasse="amniotic_sac"):
    return Objekt(klasse, konf, box)


def frame(t, *objekte, kamera=KAMERA):
    return Frame(T0 + t, kamera, tuple(objekte))


def nur(typ, ereignisse):
    return [e for e in ereignisse if e.typ == typ]


# ==============================================================================
# V0 — Fähigkeitsprüfung beim Start
# ==============================================================================

class TestV0Faehigkeit:

    def test_coco_modell_aus_env_example_meldet_beide_luecken(self):
        """Laut Tagesreport: yolov8n.onnx, Whitelist person/bus/train/horse/sheep/cow."""
        infos = faehigkeitspruefung(["person", "bus", "train", "horse", "sheep", "cow"], [], KAMERA)
        texte = " | ".join(e.nachricht for e in infos)
        assert len(infos) == 2
        assert all(e.typ == "info" and e.kuh_id is None and e.konfidenz is None for e in infos)
        assert "Austreibungserkennung nicht verfügbar" in texte
        assert "Kalbeverdacht nicht verfügbar" in texte

    def test_vertragsmodell_meldet_nichts(self):
        k = Konfig()
        assert faehigkeitspruefung(["kuh", "amniotic_sac", "calf_legs"], list(k.keypoint_namen), KAMERA) == []

    def test_nur_eine_austreibungsklasse_ist_einschraenkung(self):
        k = Konfig()
        infos = faehigkeitspruefung(["kuh", "amniotic_sac"], list(k.keypoint_namen), KAMERA)
        assert len(infos) == 1 and "eingeschränkt" in infos[0].nachricht
        assert "calf_legs" in infos[0].nachricht

    def test_fremde_keypointnamen_werden_gemeldet(self):
        """Regressionsschutz: Code-Name back_mid vs. Label-Vertrag darf nie still scheitern."""
        k = Konfig()
        fremd = ["back_mid"] + list(k.keypoint_namen[1:])
        infos = faehigkeitspruefung(["kuh", "amniotic_sac", "calf_legs"], fremd, KAMERA)
        assert len(infos) == 1
        assert k.keypoint_namen[0] in infos[0].nachricht

    def test_ohne_kuh_klasse(self):
        infos = faehigkeitspruefung(["amniotic_sac", "calf_legs"], [], KAMERA)
        assert len(infos) == 1 and "Klasse kuh fehlt" in infos[0].nachricht


# ==============================================================================
# V1 — Austreibung (Prio 1), frame-weit
# ==============================================================================

class TestV1Austreibung:

    def test_schwelle_ist_aktiver_wert(self):
        """0.80 ist AKTIV (ki-wache-kern). Änderung nur per Beschluss."""
        assert Konfig().austreibung_schwelle == 0.80
        assert set(Konfig().austreibung_klassen) == {"amniotic_sac", "calf_legs"}

    def test_fruchtblase_ohne_kuh_im_bild_loest_aus(self):
        """Liegende/verdeckte Kuh wird oft nicht erkannt — die Blase trotzdem melden."""
        e = Austreibungswaechter().verarbeite(frame(0, blase(0.91)))
        assert len(e) == 1 and e[0].typ == "austreibung" and e[0].kuh_id is None

    def test_kaelberfuesse_loesen_aus(self):
        e = Austreibungswaechter().verarbeite(frame(0, blase(0.85, klasse="calf_legs")))
        assert len(e) == 1 and e[0].typ == "austreibung"
        assert "Kälberfüße" in e[0].nachricht

    def test_schwelle_ist_strikt_groesser(self):
        s = Konfig().austreibung_schwelle
        assert Austreibungswaechter().verarbeite(frame(0, blase(s))) == []
        assert len(Austreibungswaechter().verarbeite(frame(0, blase(s + 0.001)))) == 1

    def test_meldung_im_selben_frame_ohne_verzoegerung(self):
        e = Austreibungswaechter().verarbeite(frame(0, blase()))
        assert e[0].zeit == T0

    def test_belege_tragen_den_ausloeser(self):
        """Beweispflicht (B1): Das Ereignis trägt die Detektion fürs annotierte Bild."""
        b = blase(0.93)
        e = Austreibungswaechter().verarbeite(frame(0, b))
        assert b in e[0].belege

    def test_konfidenz_ist_maximum_der_belege(self):
        e = Austreibungswaechter().verarbeite(
            frame(0, blase(0.83), blase(0.97, klasse="calf_legs", box=(490.0, 210.0, 530.0, 250.0))))
        assert len(e) == 1 and e[0].konfidenz == 0.97
        assert "Fruchtblase und Kälberfüße" in e[0].nachricht

    def test_andere_klassen_loesen_nicht_aus(self):
        assert Austreibungswaechter().verarbeite(frame(0, kuh(), Objekt("cow", 0.99, KUH_BOX))) == []


# ==============================================================================
# V2 — Episoden und Eskalation
# ==============================================================================

class TestV2Episoden:

    def test_aktive_zeitwerte(self):
        k = Konfig()
        assert k.episode_reset_sek == 1800 and k.eskalation_nach_sek == 3600

    def test_ein_alarm_statt_flut(self):
        """1 fps über 10 min = 600 Treffer -> genau ein Alarm, nicht 600 Telegram-Nachrichten."""
        w = Austreibungswaechter()
        alle = []
        for t in range(600):
            alle += w.verarbeite(frame(t, blase()))
        assert len(alle) == 1

    def test_eskalation_genau_einmal_pro_episode(self):
        w = Austreibungswaechter()
        alle = []
        for t in range(0, 7201, 60):
            alle += w.verarbeite(frame(t, blase()))
        assert len(nur("austreibung", alle)) == 1
        esk = nur("eskalation", alle)
        assert len(esk) == 1 and esk[0].zeit == T0 + 3600
        assert esk[0].nachricht.startswith("ESKALATION")

    def test_keine_eskalation_vor_60_minuten(self):
        w = Austreibungswaechter()
        alle = []
        for t in range(0, 3600, 30):
            alle += w.verarbeite(frame(t, blase()))
        assert nur("eskalation", alle) == []

    def test_eskalation_bei_unterbrochener_sicht(self):
        w = Austreibungswaechter()
        alle = []
        for t in (0, 1000, 2500, 3700):
            alle += w.verarbeite(frame(t, blase()))
        assert [e.zeit for e in nur("eskalation", alle)] == [T0 + 3700]

    def test_pause_unter_reset_bleibt_dieselbe_episode(self):
        w = Austreibungswaechter()
        assert len(w.verarbeite(frame(0, blase()))) == 1
        assert w.verarbeite(frame(1799, blase())) == []

    def test_pause_ueber_reset_startet_neue_episode(self):
        w = Austreibungswaechter()
        erste = w.verarbeite(frame(0, blase()))[0]
        zweite = w.verarbeite(frame(1801, blase()))
        assert len(zweite) == 1 and zweite[0].typ == "austreibung"
        assert zweite[0].episode_id != erste.episode_id

    def test_kameras_sind_unabhaengig(self):
        w = Austreibungswaechter()
        assert len(w.verarbeite(frame(0, blase()))) == 1
        assert len(w.verarbeite(frame(1, blase(), kamera="stallbox"))) == 1

    def test_episode_aktiv_bis_reset(self):
        w = Austreibungswaechter()
        w.verarbeite(frame(0, blase()))
        assert w.episode_aktiv(KAMERA, None, T0 + 1800)
        assert not w.episode_aktiv(KAMERA, None, T0 + 1801)


# ==============================================================================
# V3 — Kuh-Zuordnung (Anreicherung, nie Bedingung)
# ==============================================================================

class TestV3Zuordnung:

    def test_zuordnung_ueber_boxmitte(self):
        e = Austreibungswaechter().verarbeite(frame(0, kuh(7), blase(box=(400.0, 200.0, 460.0, 260.0))))
        assert e[0].kuh_id == "Kuh #7"

    def test_rand_faengt_austretende_fruchtblase(self):
        """Mitte 40 px rechts der Kuh-Box; Rand 15 % von 400 px = 60 px."""
        e = Austreibungswaechter().verarbeite(frame(0, kuh(7), blase(box=(520.0, 220.0, 560.0, 260.0))))
        assert e[0].kuh_id == "Kuh #7"

    def test_ausserhalb_bleibt_unzugeordnet_aber_alarmiert(self):
        e = Austreibungswaechter().verarbeite(frame(0, kuh(7), blase(box=(900.0, 700.0, 960.0, 760.0))))
        assert len(e) == 1 and e[0].kuh_id is None
        assert "nicht zugeordneter Kuh" in e[0].nachricht

    def test_zwei_kuehe_groesste_ueberlappung_gewinnt(self):
        links = kuh(3, box=(0.0, 100.0, 460.0, 400.0))
        rechts = kuh(9, box=(420.0, 100.0, 900.0, 400.0))
        e = Austreibungswaechter().verarbeite(frame(0, links, rechts, blase(box=(430.0, 200.0, 500.0, 260.0))))
        assert e[0].kuh_id == "Kuh #9"

    def test_coco_cow_wird_ueber_alias_zugeordnet(self):
        e = Austreibungswaechter().verarbeite(
            frame(0, kuh(5, klasse="cow"), blase(box=(400.0, 200.0, 460.0, 260.0))))
        assert e[0].kuh_id == "Kuh #5"

    def test_eigener_identitaetsaufloeser(self):
        w = Austreibungswaechter(kuh_id_von=lambda k: "Frieda" if k.track_id == 7 else None)
        e = w.verarbeite(frame(0, kuh(7), blase(box=(400.0, 200.0, 460.0, 260.0))))
        assert e[0].kuh_id == "Frieda"

    def test_zuordnungswechsel_erzeugt_hoechstens_zweiten_alarm(self):
        """Bekannte Grenze: None <-> Kuh #7 flackert -> 2 Episoden, nicht mehr."""
        w = Austreibungswaechter()
        alle = []
        for t in range(300):
            objekte = (kuh(7), blase(box=(400.0, 200.0, 460.0, 260.0))) if t % 2 else (blase(),)
            alle += w.verarbeite(frame(t, *objekte))
        assert len(nur("austreibung", alle)) == 2


# ==============================================================================
# V4 — Keypoint-Eingang (Kalbeverdacht)
# ==============================================================================

def objekt_mit(ruecken, basis, spitze, konf=(0.9, 0.9, 0.9), namen=None):
    n = namen or Konfig().keypoint_namen
    kp = {n[0]: (*ruecken, konf[0]), n[1]: (*basis, konf[1]), n[2]: (*spitze, konf[2])}
    return Objekt("kuh", 0.9, KUH_BOX, kp, track_id=1)


class TestV4Keypoints:

    def test_array_in_vertragsreihenfolge(self):
        k = Konfig()
        kp = keypoints_aus_array([[1, 2, 0.9], [3, 4, 0.8], [5, 6, 0.7]], k)
        assert list(kp) == list(k.keypoint_namen)
        assert kp[k.keypoint_namen[2]] == (5.0, 6.0, 0.7)

    def test_falsche_keypointzahl_bricht_laut_ab(self):
        with pytest.raises(ValueError):
            keypoints_aus_array([[0, 0, 1]] * 17, Konfig())       # z. B. COCO-Pose

    def test_haengender_schwanz_90_grad(self):
        assert winkel_aus_objekt(objekt_mit((100, 100), (300, 100), (300, 250)), Konfig()) == pytest.approx(90.0)

    def test_waagrecht_nach_hinten_180_grad(self):
        assert winkel_aus_objekt(objekt_mit((100, 100), (300, 100), (450, 100)), Konfig()) == pytest.approx(180.0)

    def test_entspricht_skalarprodukt_formel(self):
        rnd = random.Random(1497)
        for _ in range(200):
            r, b, s = [(rnd.uniform(0, 1000), rnd.uniform(0, 1000)) for _ in range(3)]
            u = (r[0] - b[0], r[1] - b[1])
            v = (s[0] - b[0], s[1] - b[1])
            erwartet = math.degrees(math.acos(max(-1.0, min(1.0,
                (u[0] * v[0] + u[1] * v[1]) / (math.hypot(*u) * math.hypot(*v))))))
            assert winkel_aus_objekt(objekt_mit(r, b, s), Konfig()) == pytest.approx(erwartet, abs=1e-9)

    def test_niedrige_konfidenz_ist_luecke(self):
        k = Konfig()
        o = objekt_mit((100, 100), (300, 100), (300, 250), konf=(0.9, 0.9, k.keypoint_min_konfidenz - 0.01))
        assert winkel_aus_objekt(o, k) is None

    def test_fremder_keypointname_ist_luecke(self):
        k = Konfig()
        namen = ("back_mid",) + tuple(k.keypoint_namen[1:])
        assert winkel_aus_objekt(objekt_mit((100, 100), (300, 100), (300, 250), namen=namen), k) is None

    def test_entartete_punkte_sind_luecke(self):
        assert winkel_aus_objekt(objekt_mit((100, 100), (300, 100), (300, 100)), Konfig()) is None


# ==============================================================================
# V5 — Konfiguration
# ==============================================================================

class TestV5Konfig:

    def test_unbekannter_schluessel_bricht_start_ab(self):
        with pytest.raises(ValueError):
            Konfig.aus_dict({"dominanz_antiel": 0.2})              # Tippfehler darf nicht still verpuffen

    def test_ungueltiger_anteil_bricht_ab(self):
        with pytest.raises(ValueError):
            Konfig.aus_dict({"dominanz_anteil": 1.5})

    @pytest.mark.parametrize("anteil", [0.2, 0.6])
    def test_wachmodus_halbiert_den_anteil(self, anteil):
        assert Konfig(dominanz_anteil=anteil).dominanz_effektiv == anteil
        assert Konfig(dominanz_anteil=anteil, wach_modus=True).dominanz_effektiv == pytest.approx(anteil / 2)

    def test_mindestbelegung_folgt_der_framerate(self):
        k = Konfig()
        assert k.min_frames_entscheidung(1.0) == 300              # bisheriger Codestand bei 1 fps
        assert k.min_frames_entscheidung(0.1) == 30               # Snapshot-Pfad: erreichbar
        assert Konfig(wach_modus=True).min_frames_entscheidung(1.0) == 150

    def test_framerate_null_bricht_ab(self):
        with pytest.raises(ValueError):
            Konfig().min_frames_entscheidung(0)

    def test_listen_aus_yaml_werden_tupel(self):
        k = Konfig.aus_dict({"keypoint_namen": ["a", "b", "c"], "austreibung_klassen": ["amniotic_sac"]})
        assert k.keypoint_namen == ("a", "b", "c") and k.austreibung_klassen == ("amniotic_sac",)


# ==============================================================================
# V6 — Sperre je (Kuh, Typ)
# ==============================================================================

class TestV6Sperre:

    def test_sperre_je_kuh_und_typ(self):
        s = Sperre(900)
        s.sperren("Kuh #7", "kalbeverdacht", T0)
        assert s.gesperrt("Kuh #7", "kalbeverdacht", T0 + 1)
        assert not s.gesperrt("Kuh #7", "brunstverdacht", T0 + 1)
        assert not s.gesperrt("Kuh #8", "kalbeverdacht", T0 + 1)

    def test_sperre_laeuft_ab(self):
        s = Sperre(900)
        s.sperren("Kuh #7", "kalbeverdacht", T0)
        assert not s.gesperrt("Kuh #7", "kalbeverdacht", T0 + 900)

    @pytest.mark.parametrize("typ", ["austreibung", "eskalation"])
    def test_austreibung_und_eskalation_sind_nicht_sperrbar(self, typ):
        s = Sperre(900)
        with pytest.raises(ValueError):
            s.sperren("Kuh #7", typ, T0)
        assert not s.gesperrt("Kuh #7", typ, T0)

    def test_aktive_sperre_haelt_austreibung_nicht_auf(self):
        s = Sperre(900)
        s.sperren("Kuh #7", "kalbeverdacht", T0)
        e = Austreibungswaechter().verarbeite(frame(1, kuh(7), blase(box=(400.0, 200.0, 460.0, 260.0))))
        assert len(e) == 1 and e[0].kuh_id == "Kuh #7"


# ==============================================================================
# V7 — Abbildung auf POST /api/events
# ==============================================================================

def ereignis(typ="austreibung", **kw):
    basis = dict(typ=typ, kamera=KAMERA, kuh_id="Kuh #7", zeit=T0, nachricht="Text", konfidenz=0.91)
    basis.update(kw)
    return Ereignis(**basis)


class TestV7Api:

    def test_genau_die_fuenf_vertragsfelder(self):
        assert set(api_nutzlast(ereignis())) == {"typ", "kuhId", "kamera", "nachricht", "konfidenz"}

    def test_eskalation_bis_b17_als_austreibung(self):
        n = api_nutzlast(ereignis("eskalation", nachricht="ESKALATION: …"), Konfig())
        assert n["typ"] in API_TYPEN_BASIS and n["nachricht"].startswith("ESKALATION")

    def test_eskalation_nach_b17_eigener_typ(self):
        n = api_nutzlast(ereignis("eskalation", nachricht="ESKALATION: …"), Konfig(eskalation_api_typ="eskalation"))
        assert n["typ"] == "eskalation"

    def test_unbekannter_typ_bricht_ab(self):
        with pytest.raises(ValueError):
            api_nutzlast(ereignis("lahmheit"))

    def test_leere_nachricht_bricht_ab(self):
        with pytest.raises(ValueError):
            api_nutzlast(ereignis(nachricht="   "))

    def test_konfidenz_ausserhalb_bricht_ab(self):
        with pytest.raises(ValueError):
            api_nutzlast(ereignis(konfidenz=1.2))

    def test_info_ohne_kuh_und_konfidenz(self):
        n = api_nutzlast(ereignis("info", kuh_id=None, konfidenz=None))
        assert n["kuhId"] is None and n["konfidenz"] is None

    def test_dritte_kamera_wird_nicht_gefiltert(self):
        assert api_nutzlast(ereignis(kamera="stallbox"))["kamera"] == "stallbox"

    def test_ereignis_aus_waechter_ist_api_tauglich(self):
        w = Austreibungswaechter()
        alle = []
        for t in range(0, 3601, 60):
            alle += w.verarbeite(frame(t, blase()))
        for e in alle:
            n = api_nutzlast(e)
            assert n["nachricht"] and 0.0 <= n["konfidenz"] <= 1.0
