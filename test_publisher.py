"""Manual smoke uses the authenticated HTTP route, never a direct SDK bypass."""
import json
import os
from urllib.request import Request, urlopen
from uuid import uuid4
from datetime import datetime, timezone


def run_test():
    payload = {
        'channel': os.environ['EVENT_TEST_CHANNEL'],
        'message': {
            'event_id': str(uuid4()), 'event_type': 'clinical.access.requested',
            'reference_id': str(uuid4()), 'occurred_at': datetime.now(timezone.utc).isoformat(),
        },
    }
    request = Request(os.environ['EVENT_BUS_URL'].rstrip('/') + '/publish',
                      data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json',
                               'Authorization': 'Bearer ' + os.environ['EVENT_TEST_SERVICE_TOKEN']})
    with urlopen(request, timeout=10) as response:
        print(response.status)


if __name__ == '__main__':
    run_test()
