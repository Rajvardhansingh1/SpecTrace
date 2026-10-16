from concurrent.futures import ThreadPoolExecutor

from app.adapters.store import RunStore, init_schema, make_engine


def test_in_memory_store_survives_concurrent_requests():
    """The server runs sync routes in worker threads. The in-memory database shares one connection,
    so unsynchronized use let one request's transaction roll back another's insert."""
    engine = make_engine(None)
    init_schema(engine)
    store = RunStore(engine)

    def create_and_finish(i: int) -> str:
        row = store.create(f"a{i}", f"b{i}", {"a.md": "# a"}, {"a.md": "# b"})
        store.finish(row.id, {"changes": []})
        return row.id

    def read_often(_: int) -> int:
        return sum(len(store.list()) for _ in range(40))

    with ThreadPoolExecutor(max_workers=12) as pool:
        writers = [pool.submit(create_and_finish, i) for i in range(60)]
        readers = [pool.submit(read_often, i) for i in range(6)]
        ids = [w.result() for w in writers]
        for r in readers:
            r.result()

    assert len(set(ids)) == 60
    assert all(store.get(i).status == "done" for i in ids)
