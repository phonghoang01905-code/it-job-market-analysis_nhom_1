from data_ana.bi import DASHBOARDS, provision


class FakeMetabase:
    url = "http://localhost:3000"
    def __init__(self):
        self.collections = []; self.databases = []; self.cards = []; self.dashboards = []
        self.executed = 0

    def call(self, method, path, body=None):
        if path == "/collection":
            if method == "GET": return self.collections
            row = {"id":1,**body}; self.collections.append(row); return row
        if path == "/database":
            if method == "GET": return {"data":self.databases}
            row = {"id":1,**body}; self.databases.append(row); return row
        if path.startswith("/database/"):
            self.databases[0].update(body); return self.databases[0]
        if path.endswith("/items"):
            return {"data":[{"model":"card",**c} for c in self.cards] + [{"model":"dashboard",**d} for d in self.dashboards]}
        if path.endswith("/query"):
            self.executed += 1
            return {"status":"completed"}
        target = self.cards if path.startswith("/card") else self.dashboards
        if method == "POST":
            row = {"id":len(target)+1, **body}; target.append(row); return row
        row = next(item for item in target if item["id"] == int(path.rsplit("/",1)[-1]))
        row.update(body)
        if "dashcards" in row:
            for i, card in enumerate(row["dashcards"]):
                if card["id"] < 0: card["id"] = 100+i
        return row


def test_metabase_provision_is_idempotent_and_every_card_runs_sql():
    client = FakeMetabase()
    details = {"host":"localhost", "port":55432, "dbname":"test", "user":"readonly", "password":"private"}
    first = provision(client,details)
    second = provision(client,details)
    expected = sum(len(cards) for cards in DASHBOARDS.values())
    assert first == second and len(first) == 4
    assert len(client.databases) == 1 and len(client.collections) == 1
    assert len(client.dashboards) == 4 and len(client.cards) == expected
    assert client.executed == expected*2
    assert all(link.endswith("#refresh=60") for link in first.values())
    assert "private" not in str(first)
    assert all(card["dataset_query"]["native"]["query"].startswith("SELECT") for card in client.cards)
