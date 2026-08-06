from pathlib import Path
import re

HTML = Path(__file__).parents[1] / "netaudit" / "web_static" / "academy.html"
text = HTML.read_text(encoding="utf-8")
STATIC = HTML.parent


def test_single_file_app_has_requested_surfaces():
    for phrase in [
        "Study boxes",
        "Deep-dive forums",
        "defense room",
        "Badges",
        "Kali/Linux-style terminal",
    ]:
        assert phrase.lower() in text.lower()


def test_lab_and_scenario_depth():
    assert text.count("track:'Frontend'") >= 4
    assert text.count("track:'Backend'") >= 4
    assert text.count("track:'Security'") >= 3
    assert text.count("type:'") >= 10


def test_repeat_limit_is_enforced():
    assert "(p.attackCounts[s.type]||0)<2" in text
    assert "No incident type is selected more than twice" in text


def test_no_real_shell_execution_apis():
    forbidden = ["child_process", "os.system", "subprocess", "eval(", "new Function("]
    for token in forbidden:
        assert token not in text


def test_cisa_feed_and_safety_copy():
    assert "known_exploited_vulnerabilities.json" in text
    assert "does not replay exploit code" in text


def test_navigation_is_visible_in_both_phone_surfaces():
    for page in ["index.html", "standalone.src.html"]:
        source = (STATIC / page).read_text(encoding="utf-8")
        assert 'href="./academy.html"' in source
        assert ">Academy</a>" in source
    assert 'href="./"' in text


def test_local_data_is_versioned_and_storage_failures_are_visible():
    assert "const DB_VERSION=2" in text
    assert "function migrateDB" in text
    assert "Math.min(2" in text
    assert 'id="storageWarning"' in text
    assert "memory only" in text


def test_accessibility_and_iphone_compatibility_guards():
    for marker in ['aria-modal="true"', 'aria-live="polite"', ":focus-visible"]:
        assert marker in text
    assert "findLast(" not in text
    assert ".at(" not in text
    for marker in [
        "interactive-widget=resizes-content",
        "grid-template-columns:repeat(6,minmax(0,1fr))",
        ".keyboard-open .sidebar",
        "window.visualViewport",
        "overflow-x:hidden",
    ]:
        assert marker in text


def test_phone_nav_labels_can_shrink_without_widening_the_page():
    for page in ["index.html", "standalone.src.html"]:
        source = (STATIC / page).read_text(encoding="utf-8")
        assert 'class="nav-label"' in source
        assert "min-width:0;overflow:hidden" in source


def test_terminal_is_a_draggable_persistent_utility():
    assert "['terminal','" not in text
    for marker in [
        'id="terminalFab"',
        'id="floatingTerminal"',
        "pointerdown",
        "setPointerCapture",
        "function openFloatingTerminal",
        "function renderLabDetail",
    ]:
        assert marker in text
    assert "openFloatingTerminal('${l.id}',true)" not in text
    assert ".termline input{font-size:16px}" in text


def test_boxes_open_details_and_tracking_stays_in_profile():
    assert "view='lab'" in text
    assert 'target="_blank" rel="noopener noreferrer"' in text
    assert "function boxTrackingRows" in text
    dashboard = text[text.index("function renderDashboard"):text.index("function labCard")]
    assert "Boxes complete" not in dashboard
    lab_card = text[text.index("function labCard"):text.index("function renderStudies")]
    assert "lab-progress" not in lab_card
    assert "Completed" not in lab_card


def test_box_guide_and_live_terminal_objectives_are_present():
    for marker in [
        "function labSlides",
        "function setLabSlide",
        "Guide ${labSlide+1} of ${slides.length}",
        "Build an investigation plan",
        "Ready for safe practice",
        'id="terminalObjectives"',
        "function renderTerminalObjectives",
        "renderTerminalObjectives(l);",
        "let guestLabs={}",
    ]:
        assert marker in text
