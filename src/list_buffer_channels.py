"""One-off diagnostic: list every channel connected to your Buffer account,
so you can find the X/Twitter channel's id for BUFFER_X_CHANNEL_ID.

Not wired into any workflow — run it yourself, locally, once, after
connecting X in Buffer.

Usage:
    BUFFER_API_KEY=... python -m src.list_buffer_channels
"""
import sys

from . import post_buffer

ORGANIZATIONS_QUERY = """
query GetOrganizations {
  account { organizations { id name ownerEmail } }
}
"""

CHANNELS_QUERY = """
query GetChannels($organizationId: String!) {
  channels(input: { organizationId: $organizationId }) {
    id
    name
    displayName
    service
    isQueuePaused
  }
}
"""


def _looks_like_x(service):
    s = (service or "").lower()
    return "twitter" in s or s == "x"


def main():
    try:
        org_data = post_buffer.graphql_request(ORGANIZATIONS_QUERY)
    except post_buffer.PosterNotConfigured as exc:
        print(f"Cannot list channels: {exc}")
        return 1

    orgs = (org_data.get("data") or {}).get("account", {}).get("organizations", [])
    if not orgs:
        print("No organizations found for this API key.")
        return 1

    for org in orgs:
        print(f"Organization: {org['name']} ({org['id']})")
        chan_data = post_buffer.graphql_request(CHANNELS_QUERY, {"organizationId": org["id"]})
        channels = (chan_data.get("data") or {}).get("channels", [])
        if not channels:
            print("  (no connected channels)")
            continue
        for ch in channels:
            marker = "   <-- looks like X/Twitter, use this id" if _looks_like_x(ch.get("service")) else ""
            label = ch.get("displayName") or ch.get("name") or "(unnamed)"
            print(f"  [{ch.get('service')}] {label}  id={ch['id']}{marker}")

    print()
    print("Set the X channel's id as BUFFER_X_CHANNEL_ID (GitHub repo secret).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
