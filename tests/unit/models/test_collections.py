from rootme_sdk.models.collections import Collection


def test_collection_model() -> None:
    collection = Collection(("item1", "item2"), "https://example.com/next")
    assert collection.items == ("item1", "item2")
    assert collection.next_url == "https://example.com/next"

    empty: Collection[int] = Collection(())
    assert empty.items == ()
    assert empty.next_url is None
