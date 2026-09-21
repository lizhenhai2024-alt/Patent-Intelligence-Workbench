from app.desktop.figure_preview import FigureScale, figure_scale


def test_figure_scale_fits_large_image():
    assert figure_scale(1200, 1600, 600, 600) == FigureScale(subsample=3)


def test_figure_scale_zooms_in_from_fit_baseline():
    assert figure_scale(1200, 800, 600, 400, 1) == FigureScale(subsample=1)


def test_figure_scale_zooms_above_native_size():
    assert figure_scale(400, 300, 800, 600, 2) == FigureScale(zoom=3)


def test_figure_scale_zooms_out_below_fit():
    assert figure_scale(1200, 800, 600, 400, -2) == FigureScale(subsample=4)
