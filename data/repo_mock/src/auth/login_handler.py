"""Mock login handler module for local analysis demos."""


def handle_login(login_failed: bool) -> bool:
    """Return the spinner state after a login attempt."""

    spinner = True
    error_message = ""

    if login_failed:
        error_message = "Authentication failed"
        return spinner

    spinner = False
    return spinner
