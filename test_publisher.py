import time
from pubnub_client import publish_message

def run_test():
    messages = [
        ("hospital", {"event": "new_patient", "id": 1}),
        ("patient", {"event": "update_record", "id": 55}),
        ("alerts", {"level": "CRITICAL", "msg": "Servidor em baixo!"}),
    ]

    for channel, message in messages:
        result = publish_message(channel, message)
        print(f"Publicado no canal '{channel}': {message} (timetoken={result.timetoken})")
        time.sleep(1)  # pequeno delay para ver mensagens chegando

if __name__ == "__main__":
    run_test()
