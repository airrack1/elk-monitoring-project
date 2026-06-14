from netaudit.scope import Scope


def test_cidr_in_scope():
    s = Scope(in_scope=["192.168.1.0/24"])
    assert s.check("192.168.1.50").allowed
    assert not s.check("10.0.0.1").allowed


def test_exclusion_wins():
    s = Scope(in_scope=["192.168.1.0/24"], exclusions=["192.168.1.10"])
    assert not s.check("192.168.1.10").allowed
    assert s.check("192.168.1.11").allowed


def test_range_shorthand():
    s = Scope(in_scope=["192.168.1.10-20"])
    assert s.check("192.168.1.15").allowed
    assert not s.check("192.168.1.25").allowed


def test_hostname_scope():
    s = Scope(in_scope=["dc01.client.local"])
    assert s.check("dc01.client.local").allowed
    assert not s.check("other.client.local").allowed
