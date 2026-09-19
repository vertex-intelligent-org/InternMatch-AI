from pathlib import Path

ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)


def test_why_you_match_progress_precedes_cancel_button():
    source = (
        ROOT
        / "apps/mobile/src/screens/"
        "WhyYouMatchScreen.js"
    ).read_text(
        encoding="utf-8"
    )

    progress_track = source.find(
        "<View style={styles.aiProgressTrack}>"
    )

    progress_text = source.find(
        "style={styles.aiProgressText}"
    )

    cancel_button = source.find(
        "requestExplanationCancellation()"
    )

    assert progress_track >= 0
    assert progress_text >= 0
    assert cancel_button >= 0

    assert progress_track < progress_text
    assert progress_text < cancel_button
