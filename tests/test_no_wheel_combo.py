from audioknob_gui.gui.widgets.no_wheel_combo import should_ignore_combo_wheel


def test_should_ignore_wheel_when_popup_closed() -> None:
    assert should_ignore_combo_wheel(popup_visible=False) is True


def test_should_allow_wheel_when_popup_visible() -> None:
    assert should_ignore_combo_wheel(popup_visible=True) is False
