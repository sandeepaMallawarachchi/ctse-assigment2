"""Mock login form module for local analysis demos."""


def update_submit_button(is_submitting: bool, has_error: bool) -> dict[str, bool]:
    """Return simplified UI state for the login form."""

    submit_button = {
        "loading": is_submitting,
        "disabled": is_submitting,
        "show_error": has_error,
    }
    return submit_button
