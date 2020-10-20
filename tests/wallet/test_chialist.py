from src.wallet.chialisp import *


class TestChialisp:
    def test_sexp(self):
        assert sexp() == "()"
        assert sexp(1) == "(1)"
        assert sexp(1, 2) == "(1 2)"

    def test_cons(self):
        assert cons(1, 2) == "(c 1 2)"

    def test_first(self):
        assert first("(1)") == "(f (1))"

    def test_rest(self):
        assert rest("(1)") == "(r (1))"

    def test_nth(self):
        assert nth("val") == "val"
        assert nth("val", 0) == "(f val)"
        assert nth("val", 1) == "(f (r val))"
        assert nth("val", 2) == "(f (r (r val)))"
        assert nth("val", 2, 0) == "(f (f (r (r val))))"
        assert nth("val", 2, 1) == "(f (r (f (r (r val)))))"
        assert nth("val", 2, 2) == "(f (r (r (f (r (r val))))))"

    def test_args(self):
        assert args() == "1"
        assert args(0) == "2"
        assert args(1) == "6"
        assert args(2) == "14"
        assert args(2, 0) == "28"
        assert args(2, 1) == "58"
        assert args(2, 2) == "118"

    def test_eval(self):
        assert eval("code") == "((c code 1))"
        assert eval("code", "env") == "((c code env))"

    def test_apply(self):
        assert apply("f", ()) == ("(f)")
        assert apply("f", ("1")) == ("(f 1)")
        assert apply("f", ("1", "2")) == ("(f 1 2)")

    def test_quote(self):
        assert quote(1) == "(q 1)"

    def test_make_if(self):
        assert make_if("p", "t", "f") == "((c (i p (q t) (q f)) 1))"

    def test_make_list(self):
        assert make_list() == "(q ())"
        assert make_list(1) == "(c 1 (q ()))"
        assert make_list(1, 2) == "(c 1 (c 2 (q ())))"

    def test_fail(self):
        assert fail("error") == "(x error)"

    def test_is_zero(self):
        assert is_zero("(q 1)") == "(= (q 1) (q 0))"