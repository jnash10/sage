"""
Fusion Rings
"""
# ****************************************************************************
#  Copyright (C) 2019 Daniel Bump <bump at match.stanford.edu>
#                     Guillermo Aboumrad <gh_willieab>
#                     Travis Scrimshaw <tcscrims at gmail.com>
#                     Nicolas Thiery <nthiery at users.sf.net>
#
#  Distributed under the terms of the GNU General Public License (GPL)
#                  https://www.gnu.org/licenses/
# ****************************************************************************

from itertools import product, zip_longest
from multiprocessing import Pool, set_start_method
from sage.combinat.q_analogues import q_int
import sage.combinat.root_system.f_matrix as FMatrix
from sage.combinat.root_system.fast_parallel_fusion_ring_braid_repn import collect_results, executor, _unflatten_entries
from sage.combinat.root_system.weyl_characters import WeylCharacterRing
from sage.matrix.constructor import matrix
from sage.matrix.special import diagonal_matrix
from sage.misc.cachefunc import cached_method
from sage.misc.lazy_attribute import lazy_attribute
from sage.misc.misc import inject_variable
from sage.rings.integer_ring import ZZ
from sage.rings.number_field.number_field import CyclotomicField

from sage.rings.qqbar import QQbar

class FusionRing(WeylCharacterRing):
    r"""
    Return the Fusion Ring (Verlinde Algebra) of level ``k``.

    INPUT:

    - ``ct`` -- the Cartan type of a simple (finite-dimensional) Lie algebra
    - ``k`` -- a nonnegative integer
    - ``conjugate`` -- (default ``False``) set ``True`` to obtain
      the complex conjugate ring
    - ``cyclotomic_order`` -- (default computed depending on ``ct`` and ``k``)
    - ``fusion_labels`` --  (default None) either a tuple of strings to use as labels of the
      basis of simple objects, or a string from which the labels will be
      constructed
    - ``inject_variables`` -- (default ``False``): use with ``fusion_labels``.
      If ``inject_variables`` is ``True``, the fusion labels will be variables
      that can be accessed from the command line

    The cyclotomic order is an integer `N` such that all computations
    will return elements of the cyclotomic field of `N`-th roots of unity.
    Normally you will never need to change this but consider changing it
    if :meth:`root_of_unity` ever returns ``None``.

    This algebra has a basis (sometimes called *primary fields* but here
    called *simple objects*) indexed by the weights of level `\leq k`.
    These arise as the fusion algebras of Wess-Zumino-Witten (WZW) conformal
    field theories, or as Grothendieck groups of tilting modules for quantum
    groups at roots of unity. The :class:`FusionRing` class is implemented as
    a variant of the :class:`WeylCharacterRing`.

    REFERENCES:

    - [BaKi2001]_ Chapter 3
    - [DFMS1996]_ Chapter 16
    - [EGNO2015]_ Chapter 8
    - [Feingold2004]_
    - [Fuchs1994]_
    - [Row2006]_
    - [Walton1990]_
    - [Wan2010]_

    EXAMPLES::

        sage: A22 = FusionRing("A2",2)
        sage: [f1, f2] = A22.fundamental_weights()
        sage: M = [A22(x) for x in [0*f1, 2*f1, 2*f2, f1+f2, f2, f1]]
        sage: [M[3] * x for x in M]
        [A22(1,1),
         A22(0,1),
         A22(1,0),
         A22(0,0) + A22(1,1),
         A22(0,1) + A22(2,0),
         A22(1,0) + A22(0,2)]

    You may assign your own labels to the basis elements. In the next
    example, we create the `SO(5)` fusion ring of level `2`, check the
    weights of the basis elements, then assign new labels to them while
    injecting them into the global namespace::

        sage: B22 = FusionRing("B2", 2)
        sage: b = [B22(x) for x in B22.get_order()]; b
        [B22(0,0), B22(1,0), B22(0,1), B22(2,0), B22(1,1), B22(0,2)]
        sage: [x.weight() for x in b]
        [(0, 0), (1, 0), (1/2, 1/2), (2, 0), (3/2, 1/2), (1, 1)]
        sage: B22.fusion_labels(['I0','Y1','X','Z','Xp','Y2'], inject_variables=True)
        sage: b = [B22(x) for x in B22.get_order()]; b
        [I0, Y1, X, Z, Xp, Y2]
        sage: [(x, x.weight()) for x in b]
        [(I0, (0, 0)),
         (Y1, (1, 0)),
         (X, (1/2, 1/2)),
         (Z, (2, 0)),
         (Xp, (3/2, 1/2)),
         (Y2, (1, 1))]
        sage: X * Y1
        X + Xp
        sage: Z * Z
        I0

    A fixed order of the basis keys is available with :meth:`get_order`.
    This is the order used by methods such as :meth:`s_matrix`. You may
    use :meth:`CombinatorialFreeModule.set_order` to reorder the basis::

        sage: B22.set_order([x.weight() for x in [I0,Y1,Y2,X,Xp,Z]])
        sage: [B22(x) for x in B22.get_order()]
        [I0, Y1, Y2, X, Xp, Z]

    To reset the labels, you may run :meth:`fusion_labels` with no parameter::

        sage: B22.fusion_labels()
        sage: [B22(x) for x in B22.get_order()]
        [B22(0,0), B22(1,0), B22(0,2), B22(0,1), B22(1,1), B22(2,0)]

    To reset the order to the default, simply set it to the list of basis
    element keys::

        sage: B22.set_order(B22.basis().keys().list())
        sage: [B22(x) for x in B22.get_order()]
        [B22(0,0), B22(1,0), B22(0,1), B22(2,0), B22(1,1), B22(0,2)]

    The fusion ring has a number of methods that reflect its role
    as the Grothendieck ring of a *modular tensor category* (MTC). These
    include twist methods :meth:`Element.twist` and :meth:`Element.ribbon`
    for its elements related to the ribbon structure, and the
    S-matrix :meth:`s_ij`.

    There are two natural normalizations of the S-matrix. Both
    are explained in Chapter 3 of [BaKi2001]_. The one that is computed
    by the method :meth:`s_matrix`, or whose individual entries
    are computed by :meth:`s_ij` is denoted `\tilde{s}` in
    [BaKi2001]_. It is not unitary.

    The unitary S-matrix is `s=D^{-1/2}\tilde{s}` where

    .. MATH::

        D = \sum_V d_i(V)^2.

    The sum is over all simple objects `V` with
    `d_i(V)` the *quantum dimension*. We will call quantity `D`
    the *global quantum dimension* and `\sqrt{D}` the
    *total quantum order*. They are  computed by :meth:`global_q_dimension`
    and :meth:`total_q_order`. The unitary S-matrix `s` may be obtained
    using :meth:`s_matrix` with the option ``unitary=True``.

    Let us check the Verlinde formula, which is [DFMS1996]_ (16.3). This
    famous identity states that

    .. MATH::

        N^k_{ij} = \sum_l \frac{s(i,\ell)\,s(j,\ell)\,\overline{s(k,\ell)}}{s(I,\ell)},

    where `N^k_{ij}` are the fusion coefficients, i.e. the structure
    constants of the fusion ring, and ``I`` is the unit object.
    The S-matrix has the property that if `i*` denotes the dual
    object of `i`, implemented in Sage as ``i.dual()``, then

    .. MATH::

        s(i*,j) = s(i,j*) = \overline{s(i,j)}.

    This is equation (16.5) in [DFMS1996]_. Thus with `N_{ijk}=N^{k*}_{ij}`
    the Verlinde formula is equivalent to

    .. MATH::

        N_{ijk} = \sum_l \frac{s(i,\ell)\,s(j,\ell)\,s(k,\ell)}{s(I,\ell)},

    In this formula `s` is the normalized unitary S-matrix
    denoted `s` in [BaKi2001]_. We may define a function that
    corresponds to the right-hand side, except using
    `\tilde{s}` instead of `s`::

        sage: def V(i,j,k):
        ....:     R = i.parent()
        ....:     return sum(R.s_ij(i,l) * R.s_ij(j,l) * R.s_ij(k,l) / R.s_ij(R.one(),l)
        ....:                for l in R.basis())

    This does not produce ``self.N_ijk(i,j,k)`` exactly, because of the
    missing normalization factor. The following code to check the
    Verlinde formula takes this into account::

       sage: def test_verlinde(R):
       ....:     b0 = R.one()
       ....:     c = R.global_q_dimension()
       ....:     return all(V(i,j,k) == c * R.N_ijk(i,j,k) for i in R.basis()
       ....:                for j in R.basis() for k in R.basis())

    Every fusion ring should pass this test::

        sage: test_verlinde(FusionRing("A2",1))
        True
        sage: test_verlinde(FusionRing("B4",2)) # long time (.56s)
        True

    As an exercise, the reader may verify the examples in
    Section 5.3 of [RoStWa2009]_. Here we check the example
    of the Ising modular tensor category, which is related
    to the BPZ minimal model `M(4,3)` or to an `E_8` coset
    model. See [DFMS1996]_ Sections 7.4.2 and 18.4.1.
    [RoStWa2009]_ Example 5.3.4 tells us how to
    construct it as the conjugate of the `E_8` level 2
    :class:`FusionRing`::

        sage: I = FusionRing("E8",2,conjugate=True)
        sage: I.fusion_labels(["i0","p","s"],inject_variables=True)
        sage: b = I.basis().list(); b
        [i0, p, s]
        sage: [[x*y for x in b] for y in b]
        [[i0, p, s], [p, i0, s], [s, s, i0 + p]]
        sage: [x.twist() for x in b]
        [0, 1, 1/8]
        sage: [x.ribbon() for x in b]
        [1, -1, zeta128^8]
        sage: [I.r_matrix(i, j, k) for (i,j,k) in [(s,s,i0), (p,p,i0), (p,s,s), (s,p,s), (s,s,p)]]
        [-zeta128^56, -1, -zeta128^32, -zeta128^32, zeta128^24]
        sage: I.r_matrix(s, s, i0) == I.root_of_unity(-1/8)
        True
        sage: I.global_q_dimension()
        4
        sage: I.total_q_order()
        2
        sage: [x.q_dimension()^2 for x in b]
        [1, 1, 2]
        sage: I.s_matrix()
        [                       1                        1 -zeta128^48 + zeta128^16]
        [                       1                        1  zeta128^48 - zeta128^16]
        [-zeta128^48 + zeta128^16  zeta128^48 - zeta128^16                        0]
        sage: I.s_matrix().apply_map(lambda x:x^2)
        [1 1 2]
        [1 1 2]
        [2 2 0]

    The term *modular tensor category* refers to the fact that associated
    with the category there is a projective representation of the modular
    group `SL(2,\ZZ)`. We recall that this group is generated by

    .. MATH::

        S = \begin{pmatrix} & -1\\1\end{pmatrix},\qquad
        T = \begin{pmatrix} 1 & 1\\ &1 \end{pmatrix}

    subject to the relations `(ST)^3 = S^2`, `S^2T = TS^2`, and `S^4 = I`.
    Let `s` be the normalized S-matrix, and
    `t` the diagonal matrix whose entries are the twists of the simple
    objects. Let `s` the unitary S-matrix and `t` the matrix of twists,
    and `C` the conjugation matrix :meth:`conj_matrix`. Let

    .. MATH::

        D_+ = \sum_i d_i^2 \theta_i, \qquad D_- = d_i^2 \theta_i^{-1},

    where `d_i` and `\theta_i` are the quantum dimensions and twists of the
    simple objects. Let `c` be the Virasoro central charge, a rational number
    that is computed in :meth:`virasoro_central_charge`. It is known that

    .. MATH::

        \sqrt{\frac{D_+}{D_-}} = e^{i\pi c/4}.

    It is proved in [BaKi2001]_ Equation (3.1.17) that

    .. MATH::

        (st)^3 = e^{i\pi c/4} s^2, \qquad
        s^2 = C, \qquad C^2 = 1, \qquad Ct = tC.

    Therefore `S \mapsto s, T \mapsto t` is a projective representation
    of `SL(2, \ZZ)`. Let us confirm these identities for the Fibonacci MTC
    ``FusionRing("G2", 1)``::

        sage: R = FusionRing("G2",1)
        sage: S = R.s_matrix(unitary=True)
        sage: T = R.twists_matrix()
        sage: C = R.conj_matrix()
        sage: c = R.virasoro_central_charge(); c
        14/5
        sage: (S*T)^3 == R.root_of_unity(c/4) * S^2
        True
        sage: S^2 == C
        True
        sage: C*T == T*C
        True
    """
    @staticmethod
    def __classcall__(cls, ct, k, base_ring=ZZ, prefix=None, style="coroots", conjugate=False, cyclotomic_order=None, fusion_labels=None, inject_variables=False):
        """
        Normalize input to ensure a unique representation.

        TESTS::

            sage: F1 = FusionRing('B3', 2)
            sage: F2 = FusionRing(CartanType('B3'), QQ(2), ZZ)
            sage: F3 = FusionRing(CartanType('B3'), int(2), style="coroots")
            sage: F1 is F2 and F2 is F3
            True

            sage: A23 = FusionRing('A2', 3)
            sage: TestSuite(A23).run()

            sage: B22 = FusionRing('B2', 2)
            sage: TestSuite(B22).run()

            sage: C31 = FusionRing('C3', 1)
            sage: TestSuite(C31).run()

            sage: D41 = FusionRing('D4', 1)
            sage: TestSuite(D41).run()

            sage: G22 = FusionRing('G2', 2)
            sage: TestSuite(G22).run()

            sage: F41 = FusionRing('F4', 1)
            sage: TestSuite(F41).run()

            sage: E61 = FusionRing('E6', 1)
            sage: TestSuite(E61).run()

            sage: E71 = FusionRing('E7', 1)
            sage: TestSuite(E71).run()

            sage: E81 = FusionRing('E8', 1)
            sage: TestSuite(E81).run()
        """
        return super(FusionRing, cls).__classcall__(cls, ct, base_ring=base_ring,
                                                    prefix=prefix, style=style, k=k,
                                                    conjugate=conjugate,
                                                    cyclotomic_order=cyclotomic_order,
                                                    fusion_labels=fusion_labels,
                                                    inject_variables=inject_variables)

    def _test_verlinde(self, **options):
        """
        Check the Verlinde formula for this :class:`FusionRing` instance.

        EXAMPLES::

            sage: G22 = FusionRing("G2",2)
            sage: G22._test_verlinde()
        """
        tester = self._tester(**options)
        c = self.global_q_dimension()
        i0 = self.one()
        from sage.misc.misc import some_tuples
        B = self.basis()
        for x,y,z in some_tuples(B, 3, tester._max_runs):
            v = sum(self.s_ij(x,w) * self.s_ij(y,w) * self.s_ij(z,w) / self.s_ij(i0,w) for w in B)
            tester.assertEqual(v, c * self.N_ijk(x,y,z))

    def _test_total_q_order(self, **options):
        r"""
        Check that the total quantum order is real and positive.

        The total quantum order is the positive square root
        of the global quantum dimension. This indirectly test the
        Virasoro central charge.

        EXAMPLES::

            sage: G22 = FusionRing("G2",2)
            sage: G22._test_total_q_order()
        """
        tester = self._tester(**options)
        tqo = self.total_q_order(base_coercion=False)
        tester.assertTrue(tqo.is_real_positive())
        tester.assertEqual(tqo**2, self.global_q_dimension(base_coercion=False))

    def test_braid_representation(self, **options):
        """
        Check that we can compute valid braid group representations.

        This test indirectly partially verifies the correctness of the orthogonal
        F-matrix solver.

        EXAMPLES::

            sage: F41 = FusionRing("F4",1)
            sage: F41.test_braid_representation()
            sage: B22 = FusionRing("B2",2)             # long time
            sage: B22.test_braid_representation()      # long time (~45s)
        """
        if not self.is_multiplicity_free(): # Braid group representation is not available if self is not multiplicity free
           return True
        tester = self._tester(**options)
        b = self.basis()
        #Test with different numbers of strands
        for n_strands in range(3,7):
            #Randomly select a fusing anyon. Skip the identity element, since
            #its braiding matrices are trivial
            while True:
                a = b.random_element()
                if a != self.one():
                    break
            pow = a ** n_strands
            d = pow.monomials()[0]
            #Try to find 'interesting' braid group reps i.e. skip 1-d reps
            for k, v in pow.monomial_coefficients().items():
                if v > 1:
                    d = self(k)
                break
            comp_basis, sig = self.get_braid_generators(a,d,n_strands,verbose=False)
            tester.assertTrue(len(comp_basis) > 0)
            tester.assertTrue(self.gens_satisfy_braid_gp_rels(sig))

    def fusion_labels(self, labels=None, inject_variables=False):
        r"""
        Set the labels of the basis.

        INPUT:

        - ``labels`` -- (default: ``None``) a list of strings or string
        - ``inject_variables`` -- (default: ``False``) if ``True``, then
          inject the variable names into the global namespace; note that
          this could override objects already defined

        If ``labels`` is a list, the length of the list must equal the
        number of basis elements. These become the names of
        the basis elements.

        If ``labels`` is a string, this is treated as a prefix and a
        list of names is generated.

        If ``labels`` is ``None``, then this resets the labels to the default.

        EXAMPLES::

            sage: A13 = FusionRing("A1", 3)
            sage: A13.fusion_labels("x")
            sage: fb = list(A13.basis()); fb
            [x0, x1, x2, x3]
            sage: Matrix([[x*y for y in A13.basis()] for x in A13.basis()])
            [     x0      x1      x2      x3]
            [     x1 x0 + x2 x1 + x3      x2]
            [     x2 x1 + x3 x0 + x2      x1]
            [     x3      x2      x1      x0]

        We give an example where the variables are injected into the
        global namespace::

            sage: A13.fusion_labels("y", inject_variables=True)
            sage: y0
            y0
            sage: y0.parent() is A13
            True

        We reset the labels to the default::

            sage: A13.fusion_labels()
            sage: fb
            [A13(0), A13(1), A13(2), A13(3)]
            sage: y0
            A13(0)
        """
        if labels is None:
            # Remove the fusion labels
            self._fusion_labels = None
            return

        B = self.basis()
        if isinstance(labels, str):
            labels = [labels + str(k) for k in range(len(B))]
        elif len(labels) != len(B):
            raise ValueError('invalid data')

        d = {}
        ac = self.simple_coroots()
        for j, b in enumerate(self.get_order()):
            t = tuple([b.inner_product(x) for x in ac])
            d[t] = labels[j]
            if inject_variables:
                inject_variable(labels[j], B[b])
        self._fusion_labels = d

    @cached_method
    def field(self):
        r"""
        Return a cyclotomic field large enough to
        contain the `2 \ell`-th roots of unity, as well as
        all the S-matrix entries.

        EXAMPLES::

            sage: FusionRing("A2",2).field()
            Cyclotomic Field of order 60 and degree 16
            sage: FusionRing("B2",2).field()
            Cyclotomic Field of order 40 and degree 16
        """
        # if self._field is None:
        #     self._field = CyclotomicField(4 * self._cyclotomic_order)
        # return self._field
        return CyclotomicField(4 * self._cyclotomic_order)

    def fvars_field(self):
        r"""
        Return a field containing the ``CyclotomicField`` computed by
        :meth:`field` as well as all the F-symbols of the associated
        ``FMatrix`` factory object.

        This method is only available if ``self`` is multiplicity-free.

        OUTPUT:

        Depending on the ``CartanType`` associated to ``self`` and whether
        a call to an F-matrix solver has been made, this method
        will return the same field as :meth:`field`, a ``NumberField``,
        or the ``AlgebraicField`` ``QQbar``.
        See :meth:`FMatrix.attempt_number_field_computation` for more details.

        Before running an F-matrix solver, the output of this method matches
        that of :meth:`field`. However, the output may change upon successfully
        computing F-symbols. Requesting braid generators triggers a call to
        :meth:`FMatrix.find_orthogonal_solution`, so the output of this method
        may change after such a computation.

        By default, the output of methods like :meth:`r_matrix`,
        :meth:`s_matrix`, :meth:`twists_matrix`, etc. will lie in the
        ``fvars_field``, unless the ``base_coercion`` option is set to
        ``False``.

        This method does not trigger a solver run.

        EXAMPLES::

            sage: A13 = FusionRing("A1",3,fusion_labels="a",inject_variables=True)
            sage: A13.fvars_field()
            Cyclotomic Field of order 40 and degree 16
            sage: A13.field()
            Cyclotomic Field of order 40 and degree 16
            sage: a2**4
            2*a0 + 3*a2
            sage: comp_basis, sig = A13.get_braid_generators(a2,a2,4,verbose=False)
            sage: A13.fvars_field()
            Number Field in a with defining polynomial y^32 - 8*y^30 + 18*y^28 - 44*y^26 + 93*y^24 - 56*y^22 + 2132*y^20 - 1984*y^18 + 19738*y^16 - 28636*y^14 + 77038*y^12 - 109492*y^10 + 92136*y^8 - 32300*y^6 + 5640*y^4 - 500*y^2 + 25
            sage: a2.q_dimension().parent()
            Number Field in a with defining polynomial y^32 - 8*y^30 + 18*y^28 - 44*y^26 + 93*y^24 - 56*y^22 + 2132*y^20 - 1984*y^18 + 19738*y^16 - 28636*y^14 + 77038*y^12 - 109492*y^10 + 92136*y^8 - 32300*y^6 + 5640*y^4 - 500*y^2 + 25
            sage: A13.field()
            Cyclotomic Field of order 40 and degree 16
        """
        if self.is_multiplicity_free():
            return self.fmats.field()

    def root_of_unity(self, r, base_coercion=True):
        r"""
        Return `e^{i\pi r}` as an element of ``self.field()`` if possible.

        INPUT:

        - ``r`` -- a rational number

        EXAMPLES::

            sage: A11 = FusionRing("A1",1)
            sage: A11.field()
            Cyclotomic Field of order 24 and degree 8
            sage: [A11.root_of_unity(2/x) for x in [1..7]]
            [1, -1, zeta24^4 - 1, zeta24^6, None, zeta24^4, None]
        """
        n = 2 * r * self._cyclotomic_order
        if n in ZZ:
            ret = self.field().gen() ** n
            if (not base_coercion) or (self._basecoer is None):
                return ret
            return self._basecoer(ret)
        else:
            return None

    def get_order(self):
        r"""
        Return the weights of the basis vectors in a fixed order.

        You may change the order of the basis using :meth:`CombinatorialFreeModule.set_order`

        EXAMPLES::

            sage: A15 = FusionRing("A1",5)
            sage: w = A15.get_order(); w
            [(0, 0), (1/2, -1/2), (1, -1), (3/2, -3/2), (2, -2), (5/2, -5/2)]
            sage: A15.set_order([w[k] for k in [0,4,1,3,5,2]])
            sage: [A15(x) for x in A15.get_order()]
            [A15(0), A15(4), A15(1), A15(3), A15(5), A15(2)]

        .. WARNING::

            This duplicates :meth:`get_order` from
            :class:`CombinatorialFreeModule` except the result
            is *not* cached. Caching of
            :meth:`CombinatorialFreeModule.get_order` causes inconsistent
            results after calling :meth:`CombinatorialFreeModule.set_order`.

        """
        if self._order is None:
            self.set_order(self.basis().keys().list())
        return self._order

    def some_elements(self):
        """
        Return some elements of ``self``.

        EXAMPLES::

            sage: D41 = FusionRing('D4', 1)
            sage: D41.some_elements()
            [D41(1,0,0,0), D41(0,0,1,0), D41(0,0,0,1)]
        """
        return [self.monomial(x) for x in self.fundamental_weights()
                if self.level(x) <= self._k]

    def fusion_level(self):
        r"""
        Return the level `k` of ``self``.

        EXAMPLES::

            sage: B22 = FusionRing('B2',2)
            sage: B22.fusion_level()
            2
        """
        return self._k

    def fusion_l(self):
        r"""
        Return the product `\ell = m_g(k + h^\vee)`, where `m_g` denotes the
        square of the ratio of the lengths of long to short roots of
        the underlying Lie algebra, `k` denotes the level of the FusionRing,
        and `h^\vee` denotes the dual Coxeter number of the underlying Lie
        algebra.

        This value is used to define the associated root `2\ell`-th
        of unity `q = e^{i\pi/\ell}`.

        EXAMPLES::

            sage: B22 = FusionRing('B2',2)
            sage: B22.fusion_l()
            10
            sage: D52 = FusionRing('D5',2)
            sage: D52.fusion_l()
            10
        """
        return self._l

    def virasoro_central_charge(self):
        r"""
        Return the Virasoro central charge of the WZW conformal
        field theory associated with the Fusion Ring.

        If `\mathfrak{g}` is the corresponding semisimple Lie algebra, this is

        .. MATH::

            \frac{k\dim\mathfrak{g}}{k+h^\vee},

        where `k` is the level and `h^\vee` is the dual Coxeter number.
        See [DFMS1996]_ Equation (15.61).

        Let `d_i` and `\theta_i` be the quantum dimensions and
        twists of the simple objects. By Proposition 2.3 in [RoStWa2009]_,
        there exists a rational number `c` such that
        `D_+ / \sqrt{D} = e^{i\pi c/4}`, where `D_+ = \sum d_i^2 \theta_i`
        is computed in :meth:`D_plus` and `D = \sum d_i^2 > 0` is computed
        by :meth:`global_q_dimension`. Squaring this identity and
        remembering that `D_+ D_- = D` gives

        .. MATH::

            D_+ / D_- = e^{i\pi c/2}.

        EXAMPLES::

            sage: R = FusionRing("A1", 2)
            sage: c = R.virasoro_central_charge(); c
            3/2
            sage: Dp = R.D_plus(); Dp
            2*zeta32^6
            sage: Dm = R.D_minus(); Dm
            -2*zeta32^10
            sage: Dp / Dm == R.root_of_unity(c/2)
            True
        """
        dim_g = len(self.space().roots()) + self.cartan_type().rank()
        return self._conj * self._k * dim_g / (self._k + self._h_check)

    def conj_matrix(self):
        r"""
        Return the conjugation matrix, which is the permutation matrix
        for the conjugation (dual) operation on basis elements.

        EXAMPLES::

            sage: FusionRing("A2",1).conj_matrix()
            [1 0 0]
            [0 0 1]
            [0 1 0]
        """
        b = self.basis().list()
        return matrix(ZZ, [[i == j.dual() for i in b] for j in b])

    def twists_matrix(self):
        r"""
        Return a diagonal matrix describing the twist corresponding to
        each simple object in the ``FusionRing``.

        EXAMPLES::

            sage: B21=FusionRing("B2",1)
            sage: [x.twist() for x in B21.basis().list()]
            [0, 1, 5/8]
            sage: [B21.root_of_unity(x.twist()) for x in B21.basis().list()]
            [1, -1, zeta32^10]
            sage: B21.twists_matrix()
            [        1         0         0]
            [        0        -1         0]
            [        0         0 zeta32^10]
        """
        B = self.basis()
        return diagonal_matrix(B[x].ribbon() for x in self.get_order())

    @cached_method
    def N_ijk(self, elt_i, elt_j, elt_k):
        r"""
        Return the symmetric fusion coefficient `N_{ijk}`.

        INPUT:

        - ``elt_i``, ``elt_j``, ``elt_k`` -- elements of the fusion basis

        This is the same as `N_{ij}^{k\ast}`, where `N_{ij}^k` are
        the structure coefficients of the ring (see :meth:`Nk_ij`),
        and `k\ast`` denotes the dual element. The coefficient `N_{ijk}`
        is unchanged under permutations of the three basis vectors.

        EXAMPLES::

            sage: G23 = FusionRing("G2", 3)
            sage: G23.fusion_labels("g")
            sage: b = G23.basis().list(); b
            [g0, g1, g2, g3, g4, g5]
            sage: [(x,y,z) for x in b for y in b for z in b if G23.N_ijk(x,y,z) > 1]
            [(g3, g3, g3), (g3, g3, g4), (g3, g4, g3), (g4, g3, g3)]
            sage: all(G23.N_ijk(x,y,z)==G23.N_ijk(y,z,x) for x in b for y in b for z in b)
            True
            sage: all(G23.N_ijk(x,y,z)==G23.N_ijk(y,x,z) for x in b for y in b for z in b)
            True
        """
        return (elt_i * elt_j).monomial_coefficients().get(elt_k.dual().weight(), 0)

    @cached_method
    def Nk_ij(self, elt_i, elt_j, elt_k):
        r"""
        Return the fusion coefficient `N^k_{ij}`.

        These are the structure coefficients of the fusion ring, so

        .. MATH::

            i * j = \sum_{k} N_{ij}^k k.

        EXAMPLES::

            sage: A22 = FusionRing("A2", 2)
            sage: b = A22.basis().list()
            sage: all(x*y == sum(A22.Nk_ij(x,y,k)*k for k in b) for x in b for y in b)
            True
        """
        return (elt_i * elt_j).monomial_coefficients(copy=False).get(elt_k.weight(), 0)

    @cached_method
    def s_ij(self, elt_i, elt_j, base_coercion=True):
        r"""
        Return the element of the S-matrix of this fusion ring corresponding to
        the given elements.

        This is computed using the formula

        .. MATH::

            s_{i,j} = \frac{1}{\theta_i\theta_j} \sum_k N_{ik}^j d_k \theta_k,

        where `\theta_k` is the twist and `d_k` is the quantum
        dimension. See [Row2006]_ Equation (2.2) or [EGNO2015]_
        Proposition 8.13.8.

        INPUT:

        - ``elt_i``, ``elt_j`` -- elements of the fusion basis

        EXAMPLES::

            sage: G21 = FusionRing("G2", 1)
            sage: b = G21.basis()
            sage: [G21.s_ij(x, y) for x in b for y in b]
            [1, -zeta60^14 + zeta60^6 + zeta60^4, -zeta60^14 + zeta60^6 + zeta60^4, -1]
        """
        ijtwist = elt_i.twist() + elt_j.twist()
        ret = sum(k.q_dimension(base_coercion=False) * self.Nk_ij(elt_i, k, elt_j)
                   * self.root_of_unity(k.twist() - ijtwist, base_coercion=False)
                   for k in self.basis())
        if (not base_coercion) or (self._basecoer is None):
            return ret
        return self._basecoer(ret)

    def s_ijconj(self, elt_i, elt_j, base_coercion=True):
        """
        """
        ret = self.s_ij(elt_i, elt_j, base_coercion=False).conjugate()
        if (not base_coercion) or (self._basecoer is None):
            return ret
        return self._basecoer(ret)

    def s_matrix(self, unitary=False, base_coercion=True):
        r"""
        Return the S-matrix of this fusion ring.

        OPTIONAL:

        - ``unitary`` -- (default: ``False``) set to ``True`` to obtain
          the unitary S-matrix

        Without the ``unitary`` parameter, this is the matrix denoted
        `\widetilde{s}` in [BaKi2001]_.

        EXAMPLES::

            sage: D91 = FusionRing("D9", 1)
            sage: D91.s_matrix()
            [          1           1           1           1]
            [          1           1          -1          -1]
            [          1          -1 -zeta136^34  zeta136^34]
            [          1          -1  zeta136^34 -zeta136^34]
            sage: S = D91.s_matrix(unitary=True); S
            [            1/2             1/2             1/2             1/2]
            [            1/2             1/2            -1/2            -1/2]
            [            1/2            -1/2 -1/2*zeta136^34  1/2*zeta136^34]
            [            1/2            -1/2  1/2*zeta136^34 -1/2*zeta136^34]
            sage: S*S.conjugate()
            [1 0 0 0]
            [0 1 0 0]
            [0 0 1 0]
            [0 0 0 1]
        """
        b = self.basis()
        S = matrix([[self.s_ij(b[x], b[y], base_coercion=base_coercion) for x in self.get_order()] for y in self.get_order()])
        if unitary:
            return S / self.total_q_order(base_coercion=base_coercion)
        else:
            return S

    @cached_method
    def r_matrix(self, i, j, k, base_coercion=True):
        r"""
        Return the R-matrix entry corresponding to the subobject ``k``
        in the tensor product of ``i`` with ``j``.

        .. WARNING::

            This method only gives complete information when `N_{ij}^k = 1`
            (an important special case). Tables of MTC including R-matrices
            may be found in Section 5.3 of [RoStWa2009]_ and in [Bond2007]_.

        The R-matrix is a homomorphism `i \otimes j \rightarrow j \otimes i`.
        This may be hard to describe since the object `i \otimes j`
        may be reducible. However if `k` is a simple subobject of
        `i \otimes j` it is also a subobject of `j \otimes i`. If we fix
        embeddings `k \rightarrow i \otimes j`, `k \rightarrow j \otimes i`
        we may ask for the scalar automorphism of `k` induced by the
        R-matrix. This method computes that scalar. It is possible to
        adjust the set of embeddings `k \rightarrow i \otimes j` (called
        a *gauge*) so that this scalar equals

        .. MATH::

            \pm \sqrt{\frac{ \theta_k }{ \theta_i \theta_j }}.

        If `i \neq j`, the gauge may be used to control the sign of
        the square root. But if `i = j` then we must be careful
        about the sign. These cases are computed by a formula
        of [BDGRTW2019]_, Proposition 2.3.

        EXAMPLES::

            sage: I = FusionRing("E8", 2, conjugate=True)  # Ising MTC
            sage: I.fusion_labels(["i0","p","s"], inject_variables=True)
            sage: I.r_matrix(s,s,i0) == I.root_of_unity(-1/8)
            True
            sage: I.r_matrix(p,p,i0)
            -1
            sage: I.r_matrix(p,s,s) == I.root_of_unity(-1/2)
            True
            sage: I.r_matrix(s,p,s) == I.root_of_unity(-1/2)
            True
            sage: I.r_matrix(s,s,p) == I.root_of_unity(3/8)
            True
        """
        if self.Nk_ij(i, j, k) == 0:
            return 0
        if i != j:
            ret = self.root_of_unity((k.twist(reduced=False) - i.twist(reduced=False) - j.twist(reduced=False)) / 2, base_coercion=False)
        else:
            i0 = self.one()
            B = self.basis()
            ret = sum(y.ribbon(base_coercion=False)**2 / (i.ribbon(base_coercion=False) * x.ribbon(base_coercion=False)**2)
                   * self.s_ij(i0,y,base_coercion=False) * self.s_ij(i,z,base_coercion=False) * self.s_ijconj(x,z,base_coercion=False)
                   * self.s_ijconj(k,x,base_coercion=False) * self.s_ijconj(y,z,base_coercion=False) / self.s_ij(i0,z,base_coercion=False)
                   for x in B for y in B for z in B) / (self.total_q_order(base_coercion=False)**4)
        if (not base_coercion) or (self._basecoer is None):
            return ret
        return self._basecoer(ret)

    def global_q_dimension(self, base_coercion=True):
        r"""
        Return `\sum d_i^2`, where the sum is over all simple objects
        and `d_i` is the quantum dimension. It is a positive real number.

        EXAMPLES::

            sage: FusionRing("E6",1).global_q_dimension()
            3
        """
        ret = sum(x.q_dimension(base_coercion=False)**2 for x in self.basis())
        if (not base_coercion) or (self._basecoer is None):
            return ret
        return self._basecoer(ret)

    def total_q_order(self, base_coercion=True):
        r"""
        Return the positive square root of ``self.global_q_dimension()``
        as an element of ``self.field()``.

        EXAMPLES::

            sage: F = FusionRing("G2",1)
            sage: tqo=F.total_q_order(); tqo
            zeta60^15 - zeta60^11 - zeta60^9 + 2*zeta60^3 + zeta60
            sage: tqo.is_real_positive()
            True
            sage: tqo^2 == F.global_q_dimension()
            True
        """
        c = self.virasoro_central_charge()
        ret = self.D_plus(base_coercion=False) * self.root_of_unity(-c/4,base_coercion=False)
        if (not base_coercion) or (self._basecoer is None):
            return ret
        return self._basecoer(ret)

    def D_plus(self, base_coercion=True):
        r"""
        Return `\sum d_i^2\theta_i` where `i` runs through the simple objects,
        `d_i` is the quantum dimension and `\theta_i` is the twist.

        This is denoted `p_+` in [BaKi2001]_ Chapter 3.

        EXAMPLES::

            sage: B31 = FusionRing("B3",1)
            sage: Dp = B31.D_plus(); Dp
            2*zeta48^13 - 2*zeta48^5
            sage: Dm = B31.D_minus(); Dm
            -2*zeta48^3
            sage: Dp*Dm == B31.global_q_dimension()
            True
            sage: c = B31.virasoro_central_charge(); c
            7/2
            sage: Dp/Dm == B31.root_of_unity(c/2)
            True
        """
        ret = sum((x.q_dimension(base_coercion=False))**2 * x.ribbon(base_coercion=False) for x in self.basis())
        if (not base_coercion) or (self._basecoer is None):
            return ret
        return self._basecoer(ret)


    def D_minus(self, base_coercion=True):
        r"""
        Return `\sum d_i^2\theta_i^{-1}` where `i` runs through the simple
        objects, `d_i` is the quantum dimension and `\theta_i` is the twist.

        This is denoted `p_-` in [BaKi2001]_ Chapter 3.

        EXAMPLES::

            sage: E83 = FusionRing("E8",3,conjugate=True)
            sage: [Dp,Dm] = [E83.D_plus(), E83.D_minus()]
            sage: Dp*Dm == E83.global_q_dimension()
            True
            sage: c = E83.virasoro_central_charge(); c
            -248/11
            sage: Dp*Dm == E83.global_q_dimension()
            True
        """
        ret = sum((x.q_dimension(base_coercion=False))**2 / x.ribbon(base_coercion=False) for x in self.basis())
        if (not base_coercion) or (self._basecoer is None):
            return ret
        return self._basecoer(ret)

    def is_multiplicity_free(self):
        """
        Return True if the fusion multiplicities
        :meth:`Nk_ij` are bounded by 1. The :class:`FMatrix`
        is available only for multiplicity free instances of
        :class:`FusionRing`.

        EXAMPLES::

            sage: [FusionRing(ct,k).is_multiplicity_free() for ct in ("A1","A2","B2","C3") for k in (1,2,3)]
            [True, True, True, True, True, False, True, True, False, True, False, False]

        """
        ct = self.cartan_type()
        k = self.fusion_level()
        if ct.letter == 'A':
            if ct.n == 1:
                return True
            return k <= 2
        if ct.letter in ['B','D','G','F','E']:
            return k <= 2
        if ct.letter == 'C':
            if ct.n == 2:
                return k <= 2
            return k == 1

    ###################################
    ### Braid group representations ###
    ###################################

    def get_trees(self,top_row,root):
        """
        Recursively enumerate all the admissible trees with given top row and root.

        INPUT:

        - ``top_row`` -- a list of basis elements of self
        - ``root`` -- a simple element of self

        Let `k` denote the length ``top_row``. This method returns
        Returns a list of tuples `(l_1,...,l_{k-2})` such that

        .. MATH::

            \\begin{array}{l}
            root \\to l_{k-2} \otimes m_{k},\\
            l_{k-2} \\to l_{k-3} \otimes m_{k-1},\\
            \\cdots\\
            l_2\\to l_1\otimes m_3\\
            l_1\\to m_1\otimes m_2
            \end{array}

        where `a \\to b\otimes c` means `N_{bc}^a\\neq 0`.
        """
        if len(top_row) == 2:
            m1, m2 = top_row
            return [[]] if self.Nk_ij(m1,m2,root) else []
        else:
            m1, m2 = top_row[:2]
            return [tuple([l,*b]) for l in self.basis() for b in self.get_trees([l]+top_row[2:],root) if self.Nk_ij(m1,m2,l)]

    def get_computational_basis(self,a,b,n_strands):
        """
        Return the so-called computational basis for `\\text{Hom}(b, a^n)`.

        INPUT:

        - ``a`` -- a basis element
        - ``b`` -- another basis elements
        - ``n_strands`` -- the number of strands for a braid group

        Let `n=` ``n_strands`` and let `k` be the greatest integer `\leqslant n/2`.
        The braid group acts on `\\text{Hom}(b,a^n)`. This action
        is computed in :meth:`get_braid_generators`. This method
        returns the computational basis in the form of a set of
        fusion trees. Each tree is represented by a `(n-2)`-tuple

        .. MATH::

            (m_1,\cdots,m_k,l_1,\cdots,l_{k-2})

        These are computed by :meth:`get_trees`. As a computational
        device when ``n_strands`` is odd, we pad the vector `(m_1,\cdots,m_k)`
        with an additional `m_{k+1}` equal to `a` before passing it to
        :meth:`get_trees`. This `m_{k+1}` does not appear in the output
        of this method.
        """
        comp_basis = list()
        for top in product((a*a).monomials(),repeat=n_strands//2):
            #If the n_strands is odd, we must extend the top row by a fusing anyon
            top_row = list(top)+[a]*(n_strands%2)
            comp_basis.extend(tuple([*top,*levels]) for levels in self.get_trees(top_row,b))
        return comp_basis

    @lazy_attribute
    def fmats(self):
        """
        Construct an FMatrix factory to solve the pentagon relations and
        organize the resulting F-symbols. We only need this attribute to compute
        braid group representations.
        """
        return FMatrix.FMatrix(self)

    def _emap(self,mapper,input_args,worker_pool=None):
        """
        Apply the given mapper to each element of the given input iterable and
        return the results (with no duplicates) in a list. This method applies the
        mapper in parallel if a worker_pool is provided.

        INPUT:

        - ``mapper`` -- a string specifying the name of a function defined in the
          ``fast_parallel_fusion_ring_braid_repn`` module.
        - ``input_args`` -- a tuple of arguments to be passed to mapper

        NOTES:

            If ``worker_pool`` is not provided, function maps and reduces on a
            single process.
            If ``worker_pool`` is provided, the function attempts to determine
            whether it should use multiprocessing based on the length of the
            input iterable. If it can't determine the length of the input
            iterable then it uses multiprocessing with the default chunksize of
            `1` if chunksize is not explicitly provided.
        """
        n_proc = worker_pool._processes if worker_pool is not None else 1
        input_iter = [(child_id, n_proc, input_args) for child_id in range(n_proc)]
        no_mp = worker_pool is None
        #Map phase. Casting Async Object blocks execution... Each process holds results
        #in its copy of fmats.temp_eqns
        input_iter = zip_longest([],input_iter,fillvalue=(mapper,id(self)))
        if no_mp:
            list(map(executor,input_iter))
        else:
            list(worker_pool.imap_unordered(executor,input_iter,chunksize=1))
        #Reduce phase
        if no_mp:
            results = collect_results(0)
        else:
            results = list()
            for worker_results in worker_pool.imap_unordered(collect_results,range(worker_pool._processes),chunksize=1):
                results.extend(worker_results)
            # results = list(results)
        return results

    def get_braid_generators(self,
                            fusing_anyon,
                            total_charge_anyon,
                            n_strands,
                            checkpoint=False,
                            save_results="",
                            warm_start="",
                            use_mp=True,
                            verbose=True):
        """
        Compute generators of the Artin braid group on `n=` ``n_strands``
        strands. If `a` = ``fusing_anyon`` and `b` = ``total_charge_anyon``
        the generators are endomorphisms of `\\text{Hom}(b, a^n)`.

        INPUT:

        - ``fusing_anyon`` -- a basis element of self
        - ``total_charge_anyon`` -- a basis element of self
        - ``n_strands`` -- a positive integer greater than 2
        - ``checkpoint`` -- (optional) a boolean indicating whether the
          F-matrix solver should pickle checkpoints.
        - ``save_results`` -- (optional) a string indicating the name of
          a file in which to pickle computed F-symbols for later use.
        - ``warm_start`` -- (optional) a string indicating the name of a
          pickled checkpoint file to "warm" start the F-matrix solver.
          The pickle may be a checkpoint generated by the solver, or
          a file containing solver results. If all F-symbols are known,
          we don't run the solver again.
        - ``use_mp`` -- (optional) a boolean indicating whether to use
          multiprocessing to speed up the computation. This is highly
          recommended.

        For more information on the optional parameters, see
        :meth:`find_orthogonal_solution` of the :class:`FMatrix` module.

        Given a simple object in the fusion category, here called
        ``fusing_anyon`` allowing the universal R-matrix to act on adjacent
        pairs in the fusion of ``n_strands`` copies of ``fusing_anyon``
        produces an action of the braid group. This representation can
        be decomposed over another anyon, here called ``total_charge_anyon``.
        See [CHW2015]_.

        OUTPUT:

        The method outputs a pair of data ``(comp_basis,sig)`` where
        ``comp_basis`` is a list of basis elements of the braid group
        module, parametrized by a list of fusion ring elements describing
        a fusion tree. For example with 5 strands the fusion tree
        is as follows. See :meth:`get_computational_basis` and :meth:`get_trees`
        for more information.

        .. image:: ../../../media/fusiontree.png

        ``sig`` is a list of braid group generators as matrices. In
        some cases these will be represented as sparse matrices.

        In the following example we compute a 5-dimensional braid group
        representation on 5 strands associated to the spin representation in the
        modular tensor category `SU(2)_4 \cong SO(3)_2`.

        EXAMPLES::

            sage: A14 = FusionRing("A1",4)
            sage: A14.get_order()
            [(0, 0), (1/2, -1/2), (1, -1), (3/2, -3/2), (2, -2)]
            sage: A14.fusion_labels(["one","two","three","four","five"],inject_variables=True)
            sage: [A14(x) for x in A14.get_order()]
            [one, two, three, four, five]
            sage: two ** 5
            5*two + 4*four
            sage: comp_basis, sig = A14.get_braid_generators(two,two,5,verbose=False)
            sage: A14.gens_satisfy_braid_gp_rels(sig)
            True
            sage: len(comp_basis) == 5
            True

        """
        assert int(n_strands) > 2, "The number of strands must be an integer greater than 2"
        #Construct associated FMatrix object and solve for F-symbols
        if self.fmats._chkpt_status < 7:
            self.fmats.find_orthogonal_solution(checkpoint=checkpoint,
                                                save_results=save_results,
                                                warm_start=warm_start,
                                                use_mp=use_mp,
                                                verbose=verbose)

        #Set multiprocessing parameters. Context can only be set once, so we try to set it
        try:
            set_start_method('fork')
        except RuntimeError:
            pass
        #Turn off multiprocessing when field is QQbar due to pickling issues introduced by PARI upgrade in trac ticket #30537
        pool = Pool() if use_mp and self.fvars_field() != QQbar else None

        #Set up computational basis and compute generators one at a time
        a, b = fusing_anyon, total_charge_anyon
        comp_basis = self.get_computational_basis(a,b,n_strands)
        d = len(comp_basis)
        if verbose:
            print("Computing an {}-dimensional representation of the Artin braid group on {} strands...".format(d,n_strands))

        #Compute diagonal odd-indexed generators using the 3j-symbols
        gens = { 2*i+1 : diagonal_matrix(self.r_matrix(a,a,c[i]) for c in comp_basis) for i in range(n_strands//2) }

        #Compute even-indexed generators using F-matrices
        for k in range(1,n_strands//2):
            entries = self._emap('sig_2k',(k,a,b,n_strands),pool)

            #Build cyclotomic field element objects from tuple of rationals repn
            _unflatten_entries(self, entries)

            gens[2*k] = matrix(dict(entries))

        #If n_strands is odd, we compute the final generator
        if n_strands % 2:
            entries = self._emap('odd_one_out',(a,b,n_strands),pool)

            #Build cyclotomic field element objects from tuple of rationals repn
            _unflatten_entries(self, entries)

            gens[n_strands-1] = matrix(dict(entries))

        return comp_basis, [gens[k] for k in sorted(gens)]

    def gens_satisfy_braid_gp_rels(self,sig):
        """
        Return True if the matrices in the list ``sig`` satisfy
        the braid relations. This if `n` is the cardinality of ``sig``, this
        confirms that these matrices define a representation of
        the Artin braid group on `n+1` strands.Tests correctness of
        get_braid_generators method.

        EXAMPLES::

            sage: F41 = FusionRing("F4",1,fusion_labels="f",inject_variables=True)
            sage: f1*f1
            f0 + f1
            sage: comp, sig = F41.get_braid_generators(f1,f0,4,verbose=False)
            sage: F41.gens_satisfy_braid_gp_rels(sig)
            True
        """
        n = len(sig)
        braid_rels = all(sig[i] * sig[i+1] * sig[i] == sig[i+1] * sig[i] * sig[i+1] for i in range(n-1))
        far_comm = all(sig[i] * sig[j] == sig[j] * sig[i] for i, j in product(range(n),repeat=2) if abs(i-j) > 1 and i > j)
        singular = any(s.is_singular() for s in sig)
        return braid_rels and far_comm and not singular

    class Element(WeylCharacterRing.Element):
        """
        A class for FusionRing elements.
        """
        def is_simple_object(self):
            r"""
            Determine whether ``self`` is a simple object of the fusion ring.

            EXAMPLES::

                sage: A22 = FusionRing("A2", 2)
                sage: x = A22(1,0); x
                A22(1,0)
                sage: x.is_simple_object()
                True
                sage: x^2
                A22(0,1) + A22(2,0)
                sage: (x^2).is_simple_object()
                False
            """
            return self.parent()._k is not None and len(self._monomial_coefficients) == 1

        def weight(self):
            r"""
            Return the parametrizing dominant weight in the level `k` alcove.

            This method is only available for basis elements.

            EXAMPLES::

                sage: A21 = FusionRing("A2",1)
                sage: [x.weight() for x in A21.basis().list()]
                [(0, 0, 0), (2/3, -1/3, -1/3), (1/3, 1/3, -2/3)]
            """
            if len(self._monomial_coefficients) != 1:
                raise ValueError("fusion weight is valid for basis elements only")
            return next(iter(self._monomial_coefficients))

        def twist(self, reduced=True):
            r"""
            Return a rational number `h` such that `\theta = e^{i \pi h}`
            is the twist of ``self``. The quantity `e^{i \pi h}` is
            also available using :meth:`ribbon`.

            This method is only available for simple objects. If
            `\lambda` is the weight of the object, then
            `h = \langle \lambda, \lambda+2\rho \rangle`, where
            `\rho` is half the sum of the positive roots.
            As in [Row2006]_, this requires normalizing
            the invariant bilinear form so that
            `\langle \alpha, \alpha \rangle = 2` for short roots.

            INPUT:

            - ``reduced`` -- (default: ``True``) boolean; if ``True``
              then return the twist reduced modulo 2

            EXAMPLES::

                sage: G21 = FusionRing("G2", 1)
                sage: [x.twist() for x in G21.basis()]
                [0, 4/5]
                sage: [G21.root_of_unity(x.twist()) for x in G21.basis()]
                [1, zeta60^14 - zeta60^4]
                sage: zeta60 = G21.field().gen()
                sage: zeta60^((4/5)*(60/2))
                zeta60^14 - zeta60^4

                sage: F42 = FusionRing("F4", 2)
                sage: [x.twist() for x in F42.basis()]
                [0, 18/11, 2/11, 12/11, 4/11]

                sage: E62 = FusionRing("E6", 2)
                sage: [x.twist() for x in E62.basis()]
                [0, 26/21, 12/7, 8/21, 8/21, 26/21, 2/3, 4/7, 2/3]
            """
            if not self.is_simple_object():
                raise ValueError("quantum twist is only available for simple objects of a FusionRing")
            P = self.parent()
            rho = P.space().rho()
            # We copy self.weight() to skip the test (which was already done
            #   by self.is_simple_object()).
            lam = next(iter(self._monomial_coefficients))
            inner = lam.inner_product(lam + 2*rho)
            twist = P._conj * P._nf * inner / P.fusion_l()
            # Reduce modulo 2
            if reduced:
                f = twist.floor()
                twist -= f
                return twist + (f % 2)
            else:
                return twist

        def ribbon(self,base_coercion=True):
            r"""
            Return the twist or ribbon element of ``self``.

            If `h` is the rational number modulo 2 produced by
            ``self.twist()``, this  method produces `e^{i\pi h}`.

            .. SEEALSO::

                An additive version of this is available as :meth:`twist`.

            EXAMPLES::

                sage: F = FusionRing("A1",3)
                sage: [x.twist() for x in F.basis()]
                [0, 3/10, 4/5, 3/2]
                sage: [x.ribbon() for x in F.basis()]
                [1, zeta40^6, zeta40^12 - zeta40^8 + zeta40^4 - 1, -zeta40^10]
                sage: [F.root_of_unity(x) for x in [0, 3/10, 4/5, 3/2]]
                [1, zeta40^6, zeta40^12 - zeta40^8 + zeta40^4 - 1, -zeta40^10]
            """
            ret = self.parent().root_of_unity(self.twist(),base_coercion=False)
            if (not base_coercion) or (self.parent()._basecoer is None):
                return ret
            return self.parent()._basecoer(ret)

        @cached_method
        def q_dimension(self, base_coercion=True):
            r"""
            Return the quantum dimension as an element of the cyclotomic
            field of the `2\ell`-th roots of unity, where `l = m (k+h^\vee)`
            with `m=1,2,3` depending on whether type is simply, doubly or
            triply laced, `k` is the level and `h^\vee` is the dual
            Coxeter number.

            EXAMPLES::

                sage: B22 = FusionRing("B2",2)
                sage: [(b.q_dimension())^2 for b in B22.basis()]
                [1, 4, 5, 1, 5, 4]
            """
            if not self.is_simple_object():
                raise ValueError("quantum dimension is only available for simple objects of a FusionRing")
            P = self.parent()
            lam = self.weight()
            space = P.space()
            rho = space.rho()
            powers = {}
            for alpha in space.positive_roots():
                val = alpha.inner_product(lam + rho)
                if val in powers:
                    powers[val] += 1
                else:
                    powers[val] = 1
                val = alpha.inner_product(rho)
                if val in powers:
                    powers[val] -= 1
                else:
                    powers[val] = -1
            R = ZZ['q']
            q = R.gen()
            expr = R.fraction_field().one()
            for val in powers:
                exp = powers[val]
                if exp > 0:
                    expr *= q_int(P._nf * val, q)**exp
                elif exp < 0:
                    expr /= q_int(P._nf * val, q)**(-exp)
            expr = R(expr)
            expr = expr.substitute(q=q**4) / (q**(2*expr.degree()))
            zet = P.field().gen() ** (P._cyclotomic_order/P._l)
            ret = expr.substitute(q=zet)

            if (not base_coercion) or (self.parent()._basecoer is None):
                return ret
            return self.parent()._basecoer(ret)
