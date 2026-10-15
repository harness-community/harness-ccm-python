def synthetic_label(bucket: str, number: int, serial: int) -> str:
    return f"{bucket} account {number:02d} ({serial:012d})"


def synthetic_buckets(buckets: list, serial: int = 100000000001) -> list:
    built = []
    for entry in buckets:
        labels = []
        count = int(entry["accounts"])
        for number in range(1, count + 1):
            labels.append(synthetic_label(entry["name"], number, serial))
            serial += 1
        built.append({"name": entry["name"], "labels": labels})
    return built
