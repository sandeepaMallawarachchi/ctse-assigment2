async function updateProfile(api, payload, setSaving, setMessage) {
  setSaving(true);
  setMessage("");

  try {
    const response = await api.updateProfile(payload);

    if (!response.ok) {
      setMessage("Profile update failed");
      return false;
    }

    setMessage("Profile updated successfully");
    setSaving(false);
    return true;
  } catch (error) {
    setMessage("Network error");
    return false;
  }
}
