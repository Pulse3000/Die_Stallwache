# -*- coding: utf-8 -*-
"""
Ende-zu-Ende-Test des Stall-Labelers im echten Browser (Chromium, headless) bis in den Konverter:
ZIP öffnen -> Vorannotation laden -> Punkte per Tastatur setzen, Box löschen/zeichnen -> geprüft -> Export
-> cvat_zu_yolo_pose übernimmt nur geprüfte Bilder, paart Box und Skelett über die group_id.
Wird übersprungen, wenn Playwright/Chromium fehlt (z. B. auf dem Hof-Rechner).
"""
import csv
import os
import sys
import zipfile

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "werkzeuge"))
import cvat_zu_yolo_pose as konv  # noqa: E402

pw = pytest.importorskip("playwright.sync_api")
LABELER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "labeler", "stall_labeler.html"))
W, H = 1280, 720
BILDER = ["20261012-100000.jpg", "20261012-100200.jpg", "20261012-100400.jpg", "20261013-100000.jpg"]


def _bild(i):
    rng = np.random.default_rng(i)
    img = rng.integers(40, 90, (H, W, 3), dtype=np.uint8)
    cv2.ellipse(img, (420, 360), (220, 110), 0, 0, 360, (60, 90, 150), -1)
    cv2.putText(img, f"Bild {i}", (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 4)
    return cv2.imencode(".jpg", img)[1].tobytes()


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # pragma: no cover
            pytest.skip(f"Chromium nicht startbar: {e}")
        yield b
        b.close()


@pytest.fixture
def daten(tmp_path):
    ordner = tmp_path / "aufnahmen"
    ordner.mkdir()
    zpfad = tmp_path / "train_01.zip"
    with zipfile.ZipFile(zpfad, "w", zipfile.ZIP_STORED) as zf:
        for i, n in enumerate(BILDER):
            daten_ = _bild(i)
            zf.writestr(n, daten_)
            (ordner / n).write_bytes(daten_)
    xml = ['<?xml version="1.0" encoding="utf-8"?><annotations><version>1.1</version>']
    for i, n in enumerate(BILDER):
        xml.append(f'<image id="{i}" name="{n}" width="{W}" height="{H}">')
        if i == 0:
            xml.append('<box label="kuh" source="auto" occluded="0" xtl="180" ytl="230" xbr="680" ybr="500" z_order="0"></box>')
        if i == 1:
            xml.append('<box label="kuh" source="auto" occluded="0" xtl="180" ytl="230" xbr="680" ybr="500" z_order="0"></box>')
            xml.append('<box label="kuh" source="auto" occluded="0" xtl="900" ytl="100" xbr="1000" ybr="200" z_order="0"></box>')
        xml.append("</image>")
    xml.append("</annotations>")
    vpfad = tmp_path / "train_01_vorannotation.xml"
    vpfad.write_text("".join(xml))
    mpfad = tmp_path / "manifest.csv"
    with open(mpfad, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["datei", "stalltag", "split", "task", "licht", "defekt_anteil"])
        for n in BILDER:
            w.writerow([n, konv.stalltag(n), "val" if n.startswith("20261013") else "train", "train_01", "Tag", 0.0])
    return {"tmp": tmp_path, "zip": str(zpfad), "xml": str(vpfad), "manifest": str(mpfad), "bilder": str(ordner)}


def _schirm(page, x, y):
    """Bildkoordinaten -> Seitenkoordinaten (über die Ansichtstransformation des Labelers)."""
    return page.evaluate("""([x, y]) => {
        const r = document.getElementById('buehne').getBoundingClientRect();
        const [sx, sy] = window.__stallLabeler.zuSchirm(x, y);
        return [r.left + sx, r.top + sy];
    }""", [x, y])


def _taste_an(page, x, y, taste):
    page.mouse.move(*_schirm(page, x, y))
    page.keyboard.press(taste)


def _warte_bild(page, index):
    page.wait_for_function(f"""() => {{ const S = window.__stallLabeler.S;
        return S.index === {index} && S.bitmapName === S.namen[{index}]; }}""")


def test_labeln_exportieren_konvertieren(browser, daten):
    ctx = browser.new_context(viewport={"width": 1400, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    fehler = []
    page.on("pageerror", lambda e: fehler.append(str(e)))
    page.goto("file://" + LABELER)
    page.set_input_files("#zipWahl", daten["zip"])
    page.wait_for_function("() => window.__stallLabeler.S.namen.length === 4")
    _warte_bild(page, 0)
    page.set_input_files("#xmlWahl", daten["xml"])
    page.wait_for_function("() => (window.__stallLabeler.S.bilder['20261012-100000.jpg'] || {objekte: []}).objekte.length === 1")

    # Bild 1: Vorschlag wählen, drei Punkte (tail_tip verdeckt), geprüft & weiter
    page.mouse.click(*_schirm(page, 430, 360))
    _taste_an(page, 220, 300, "Digit1")
    _taste_an(page, 600, 310, "Digit2")
    _taste_an(page, 640, 470, "Shift+Digit3")
    page.keyboard.press("Enter")
    _warte_bild(page, 1)

    # Bild 2: kleine Fehl-Box löschen, Kuh mit 2 Punkten + tail_tip "nicht sichtbar", neue Box zeichnen
    page.mouse.click(*_schirm(page, 950, 150))
    page.keyboard.press("Delete")
    page.mouse.click(*_schirm(page, 430, 360))
    _taste_an(page, 230, 300, "Digit1")
    _taste_an(page, 590, 300, "Digit2")
    page.keyboard.press("KeyE")
    page.keyboard.press("KeyN")
    page.mouse.move(*_schirm(page, 800, 300))
    page.mouse.down()
    page.mouse.move(*_schirm(page, 1100, 600), steps=5)
    page.mouse.up()
    _taste_an(page, 850, 350, "Digit1")
    page.keyboard.press("Enter")
    _warte_bild(page, 2)

    # Bild 3 bleibt ungeprüft; Bild 4 (Val) leer, aber geprüft
    page.keyboard.press("ArrowRight")
    _warte_bild(page, 3)
    page.keyboard.press("Enter")

    with page.expect_download() as dl_info:
        page.keyboard.press("Control+KeyS")
    export = daten["tmp"] / "export.xml"
    dl_info.value.save_as(str(export))
    assert not fehler, fehler

    # Persistenz: neu laden, Paket erneut öffnen -> Stand ist da
    page.reload()
    page.set_input_files("#zipWahl", daten["zip"])
    page.wait_for_function("() => window.__stallLabeler.S.namen.length === 4")
    gepr = page.evaluate("() => Object.values(window.__stallLabeler.S.bilder).filter(b => b.geprueft).length")
    assert gepr == 3
    ctx.close()

    # Konverter: nur geprüfte Bilder, Paarung über group_id, Sichtbarkeiten korrekt
    aus = daten["tmp"] / "ds"
    b = konv.konvertiere([str(export)], daten["bilder"], daten["manifest"], str(aus), max_seite=0, beilagen=[])
    assert b["uebersprungen"].get("ungeprueft") == 1
    assert b["fehler_anzahl"] == 0
    z1 = [list(map(float, l.split())) for l in (aus / "labels" / "train" / "20261012-100000.txt").read_text().split("\n") if l]
    assert len(z1) == 1
    kp = z1[0][5:]
    assert kp[0] == pytest.approx(220 / W, abs=2 / W) and kp[1] == pytest.approx(300 / H, abs=2 / H) and kp[2] == 2
    assert kp[3] == pytest.approx(600 / W, abs=2 / W) and kp[5] == 2
    assert kp[6] == pytest.approx(640 / W, abs=2 / W) and kp[8] == 1          # verdeckt
    z2 = sorted([list(map(float, l.split())) for l in (aus / "labels" / "train" / "20261012-100200.txt").read_text().split("\n") if l])
    assert len(z2) == 2                                                          # Fehl-Box gelöscht, neue Box da
    alt, neu = sorted(z2, key=lambda z: z[1])
    assert alt[5:] [6:] == [0.0, 0.0, 0.0] and alt[7] == 2 and alt[10] == 2      # tail_tip nicht sichtbar
    assert neu[1] == pytest.approx(950 / W, abs=3 / W) and neu[7] == 2           # neue Box mit spine_end
    assert not (aus / "labels" / "train" / "20261012-100400.txt").exists()       # ungeprüft -> nicht im Datensatz
    assert (aus / "labels" / "val" / "20261013-100000.txt").read_text() == ""    # geprüft und leer -> Negativbeispiel


def test_vorhandene_arbeit_wird_beim_import_nicht_ueberschrieben(browser, daten):
    ctx = browser.new_context(viewport={"width": 1300, "height": 850})
    page = ctx.new_page()
    page.goto("file://" + LABELER)
    page.set_input_files("#zipWahl", daten["zip"])
    _warte_bild(page, 0)
    page.set_input_files("#xmlWahl", daten["xml"])
    page.wait_for_function("() => (window.__stallLabeler.S.bilder['20261012-100000.jpg'] || {objekte: []}).objekte.length === 1")
    page.keyboard.press("Enter")                       # Bild 1 geprüft
    page.set_input_files("#xmlWahl", daten["xml"])      # erneuter Import -> Nachfrage
    page.wait_for_selector("#mLeer")
    page.click("#mLeer")                                # nur leere Bilder füllen
    assert page.evaluate("() => window.__stallLabeler.S.bilder['20261012-100000.jpg'].geprueft") is True
    ctx.close()


# ----------------------------------------------------------------------------- QA Runde 5
def test_gehaltene_enter_taste_hakt_keine_ungesehenen_bilder_ab(browser, daten):
    ctx = browser.new_context(viewport={"width": 1300, "height": 850})
    page = ctx.new_page()
    page.goto("file://" + LABELER)
    page.set_input_files("#zipWahl", daten["zip"])
    _warte_bild(page, 0)
    page.keyboard.down("Enter")          # erster Druck: Bild 1 geprüft, weiter zu Bild 2
    page.keyboard.down("Enter")          # Tastenwiederholung (repeat=true): darf Bild 2 NICHT abhaken
    page.keyboard.down("Enter")
    page.keyboard.up("Enter")
    _warte_bild(page, 1)
    gepr = page.evaluate("() => window.__stallLabeler.S.namen.map(n => !!(window.__stallLabeler.S.bilder[n] || {}).geprueft)")
    assert gepr == [True, False, False, False]
    # Enter auf geprüftem Bild nimmt NICHT zurück; ⇧+Enter schon
    page.keyboard.press("ArrowLeft")
    _warte_bild(page, 0)
    page.keyboard.press("Enter")
    _warte_bild(page, 1)
    assert page.evaluate("() => window.__stallLabeler.S.bilder['20261012-100000.jpg'].geprueft") is True
    page.keyboard.press("ArrowLeft")
    _warte_bild(page, 0)
    page.keyboard.press("Shift+Enter")
    assert page.evaluate("() => window.__stallLabeler.S.bilder['20261012-100000.jpg'].geprueft") is False
    ctx.close()


def test_zweiter_tab_sperrt_den_ersten_und_nichts_wird_ueberschrieben(browser, daten):
    ctx = browser.new_context(viewport={"width": 1300, "height": 850})
    alt = ctx.new_page()
    alt.goto("file://" + LABELER)
    alt.set_input_files("#zipWahl", daten["zip"])
    _warte_bild(alt, 0)
    alt.keyboard.press("Enter")                         # alter Tab: 1 Bild geprüft
    _warte_bild(alt, 1)
    neu = ctx.new_page()
    neu.goto("file://" + LABELER)
    neu.set_input_files("#zipWahl", daten["zip"])        # übernimmt den Stand und meldet Besitz an
    neu.wait_for_function("() => window.__stallLabeler.S.namen.length === 4")
    alt.wait_for_function("() => window.__stallLabeler.S.gesperrt === true")
    _warte_bild(neu, 1)
    neu.keyboard.press("Enter")
    _warte_bild(neu, 2)                                  # Enter wirkt nur auf ein angezeigtes Bild
    neu.keyboard.press("Enter")                          # neuer Tab: insgesamt 3 geprüft
    neu.wait_for_function("() => Object.values(window.__stallLabeler.S.bilder).filter(b => b.geprueft).length === 3")
    neu.wait_for_timeout(600)                            # Autosave
    alt.keyboard.press("Enter")                          # im gesperrten Tab wirkungslos
    alt.close(run_before_unload=True)                    # Schließen darf den neueren Stand nicht überschreiben
    stand = neu.evaluate("""() => { const d = JSON.parse(localStorage.getItem('stall-labeler:v1:train_01'));
        return Object.values(d.bilder).filter(b => b.geprueft).length; }""")
    assert stand == 3
    ctx.close()


def test_rueckgaengig_auf_qwertz_und_keine_netzzugriffe(browser, daten):
    ctx = browser.new_context(viewport={"width": 1300, "height": 850}, accept_downloads=True)
    page = ctx.new_page()
    anfragen = []
    page.on("request", lambda r: anfragen.append(r.url) if not r.url.startswith(("file:", "blob:", "data:")) else None)
    page.goto("file://" + LABELER)
    page.set_input_files("#zipWahl", daten["zip"])
    _warte_bild(page, 0)
    page.set_input_files("#xmlWahl", daten["xml"])
    page.wait_for_function("() => (window.__stallLabeler.S.bilder['20261012-100000.jpg'] || {objekte: []}).objekte.length === 1")
    page.mouse.click(*_schirm(page, 430, 360))
    page.keyboard.press("Delete")
    assert page.evaluate("() => window.__stallLabeler.S.bilder['20261012-100000.jpg'].objekte.length") == 0
    # deutsche Tastatur: Taste "Z" liefert code KeyY, key "z"
    page.evaluate("""() => window.dispatchEvent(new KeyboardEvent('keydown', {key: 'z', code: 'KeyY', ctrlKey: true, bubbles: true}))""")
    assert page.evaluate("() => window.__stallLabeler.S.bilder['20261012-100000.jpg'].objekte.length") == 1
    # "Alles ersetzen" legt vorher eine Sicherung an (Download)
    page.keyboard.press("Enter")
    page.set_input_files("#xmlWahl", daten["xml"])
    page.wait_for_selector("#mAlles")
    with page.expect_download() as dl:
        page.click("#mAlles")
    assert dl.value.suggested_filename.endswith("_sicherung.xml")
    assert anfragen == [], anfragen
    ctx.close()
