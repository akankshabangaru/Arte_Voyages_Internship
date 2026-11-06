import csv

def test_trips_csv_has_all_five_countries():
    rows = list(csv.DictReader(open("trips.csv")))
    assert {r["country"] for r in rows} == {"India", "Nepal", "Bhutan", "Sri Lanka", "Maldives"}
    assert all(r["trip_id"] and r["lat"] and r["lon"] and r["start_date"] < r["end_date"] for r in rows)
