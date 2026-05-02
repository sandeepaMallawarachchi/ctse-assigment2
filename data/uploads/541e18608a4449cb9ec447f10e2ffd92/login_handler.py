def handle_login(api_client, username, password, ui_state):
    """Attempt login and update UI state."""

    ui_state["is_submitting"] = True
    ui_state["error"] = ""

    response = api_client.login(username=username, password=password)

    if response.get("success"):
        ui_state["user"] = response.get("user")
        ui_state["is_submitting"] = False
        return True

    ui_state["error"] = response.get("message", "Login failed")
    return False
