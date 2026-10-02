"""
Motor Wyckoff — port a Python del motor de "Wyckoff ES [theUltimator5]" (Pine v6).
Solo el motor de detección (fases A-E, eventos, entradas, plan SL/TP). Sin dibujos.
Semántica `na` de Pine = NaN. Se procesa vela cerrada a vela cerrada (add_bar).
"""
import math

NA = float("nan")


def na(x):
    return x != x


def nz(x, d=0.0):
    return d if x != x else x


def pmax(*a):
    return NA if any(x != x for x in a) else max(a)


def pmin(*a):
    return NA if any(x != x for x in a) else min(a)


def pround(x):
    return math.floor(x + 0.5)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ── constantes del script (ajustes fijos) ──
pivotLen = 4
adaptiveSwingMin, adaptiveSwingMax, adaptiveSwingVolLen = 2, 10, 50
trendLen, priorTrendMaxBars, priorTrendPivotFactor = 25, 200, 8.0
priorTrendStrong, priorTrendNeutral = 35.0, 15.0
continuationTrendLen, oppositeCycleMinBars, extremeLen = 200, 25, 30
phaseAMinBars, phaseAAfterArMaxBars, phaseBIdleMaxBars, phaseCIdleMaxBars = 6, 45, 125, 50
phaseAPrematureDepartureBars, phaseAPrematureDepartureTRFrac, phaseAPrematureDepartureATR = 3, 0.30, 0.75
structureInvalidationATR, structureInvalidationBars = 0.50, 2
phaseBDepartureBars, phaseBDepartureTRFrac, phaseBDepartureATR = 3, 0.35, 0.75
phaseDFailBars, phaseEMaxBars = 3, 300
volLen, atrLen = 50, 14
climaxVolMult, climaxSpreadMult, relaxedClimaxFactor = 1.8, 1.5, 0.80
prelimVolMult, prelimExtremeATR, prelimEfficiencyLookback, prelimEfficiencyRatio, prelimMinScore = 1.25, 0.75, 10, 0.80, 4
scCloseMin, bcCloseMax, climaxMinScore = 0.35, 0.65, 5
climaxAbsorptionMinBars, climaxAbsorptionMaxBars = 3, 8
climaxAbsorptionExtremeATR, climaxAbsorptionReboundATR, climaxAbsorptionVolFloor = 0.50, 0.35, 0.90
minARATR, maxARBars, arMaxExtensionATR = 2.0, 30, 15.0
boundaryTolATR, stMaxVolRatio, stMaxSpreadRatio, stMinScore = 0.75, 0.90, 0.90, 4
minPhaseBBars, minPhaseBTests, minPhaseBOppositeTests, minPhaseBTraversals = 30, 2, 1, 2
phaseBZoneFrac, phaseBRangeMinATR, phaseBRangeMaxATR = 0.25, 1.5, 8.0
phaseBBadTestCooldownFactor, phaseBEdgeExpansionCap = 2.0, 0.15
terminalTestMinBarsAfterST, terminalTestVolRatio, terminalTestSpreadRatio, terminalTestOtherMaxRatio = 3, 0.85, 0.85, 1.05
excursionRecoveryBars, springMinPenATR, springMaxPenATR = 3, 0.15, 2.5
springCloseMin, utadCloseMax, springEffortMaxMult, excursionMinScore = 0.55, 0.45, 1.50, 3
testTolATR, testMaxVolRatio, testMaxSpreadRatio, testExtremeToleranceATR, testMinScore = 1.25, 0.80, 0.80, 0.15, 2
phaseCToDMinBars, phaseDMinBars, phaseDValidationMin, phaseDDominanceFrac = 3, 4, 60, 0.65
breakATR, strengthVolMult, strengthSpreadATR = 0.15, 1.15, 1.15
sosCloseMin, sowCloseMax, strengthMinScore = 0.65, 0.35, 3
sosMultiBarLen, sosMultiBarATR, sosMultiBarEffort = 5, 2.0, 1.10
lpsBoundaryATR, lpsVolMult, lpsSpreadATR, lpsMinScore = 1.50, 1.00, 1.00, 2
confirmBars, directAcceptanceBars, directAcceptanceConfidence = 3, 5, 75
minConfidencePhaseC, minConfidencePhaseD = 45, 55
ENTRY_CONF = {"conservative": 75, "standard": 60, "aggressive": 55}
ENTRY_TESTS = {"conservative": 7, "standard": 6, "aggressive": 5}

DIR_NONE, DIR_ACCUM, DIR_DIST = 0, 1, -1
TYPE_NONE, TYPE_ACCUM, TYPE_REACCUM, TYPE_DIST, TYPE_REDIST = 0, 1, 2, -1, -2
REGIME_NONE, REGIME_MARKUP, REGIME_MARKDOWN = 0, 1, -1
PHASE_NONE, PHASE_A, PHASE_B, PHASE_C, PHASE_D, PHASE_E = 0, 1, 2, 3, 4, 5
EV_NONE, EV_SC, EV_BC, EV_AR, EV_ST, EV_SPRING, EV_UTAD, EV_TEST, EV_SOS, EV_SOW, EV_LPS, EV_LPSY, \
    EV_CTEST_ACC, EV_CTEST_DST, EV_MARKUP, EV_MARKDOWN = range(16)
TEST_NONE, TEST_GOOD, TEST_POOR, TEST_FAILED = 0, 1, 2, 3
ENTRY_NONE, ENTRY_TEST, ENTRY_STRENGTH, ENTRY_LPS, ENTRY_PHASE_E = 0, 1, 2, 3, 4
BIT_PS, BIT_SC, BIT_BC, BIT_AR, BIT_ST, BIT_SPRING, BIT_UTAD, BIT_TEST, BIT_SOS, BIT_SOW, BIT_LPS, BIT_LPSY, BIT_E = \
    1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096
BIT_CTEST = 16384
RS_INVALID, RS_ABSORB, RS_NORANGE, RS_DEPART, RS_STALE, RS_DEMOTE, RS_EEND = range(7)

PHASE_NAMES = {0: "-", 1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}
ENTRY_KIND_NAMES = {ENTRY_TEST: "Test Fase C", ENTRY_STRENGTH: "SOS/SOW", ENTRY_LPS: "LPS/LPSY", ENTRY_PHASE_E: "Fase E"}


class PT:
    def __init__(self):
        self.b1 = self.t1 = self.p1 = self.b2 = self.t2 = self.p2 = self.b3 = self.t3 = self.p3 = NA


class WS:
    def __init__(self):
        self.stopSide = 0; self.outcome = 0; self.phase = 0; self.ev = 0
        self.startBar = NA; self.pivLen = NA; self.birthTrend = NA
        self.ctxBull = False; self.ctxBear = False
        self.climaxBar = NA; self.climaxTime = NA; self.climaxPrice = NA
        self.climaxEff = NA; self.climaxSpr = NA; self.climaxATR = NA; self.climaxScore = 0
        self.absorbed = False
        self.psTime = NA; self.psPrice = NA; self.psScore = 0
        self.origHigh = NA; self.origLow = NA; self.rangeHigh = NA; self.rangeLow = NA
        self.arRunPrice = NA; self.arRunBar = NA; self.arRunTime = NA
        self.arOK = False; self.arBar = NA; self.arTime = NA; self.arPrice = NA
        self.stCount = 0; self.stN = 0; self.stEffSum = 0.0; self.stSprSum = 0.0
        self.lastGoodEff = NA; self.lastGoodSpr = NA
        self.stBar = NA; self.stTime = NA; self.stPrice = NA; self.stHist = PT(); self.stScore = 0
        self.edge1 = self.edge2 = self.edge3 = NA
        self.oppCount = 0; self.opN = 0; self.opEffSum = 0.0; self.opSprSum = 0.0
        self.opLastBar = NA; self.opLastPrice = NA; self.opHist = PT()
        self.travCount = 0; self.lastZone = 0; self.lastZoneBar = NA; self.lastBadBar = NA
        self.bStartBar = NA; self.bStartTime = NA; self.cStartTime = NA; self.cReadyBar = NA
        self.dStartBar = NA; self.dStartTime = NA; self.eStartBar = NA; self.eStartTime = NA
        self.pend = False; self.pendEdge = 0; self.pendStartBar = NA; self.pendExtBar = NA
        self.pendExt = NA; self.pendExtTime = NA; self.pendEff = NA; self.pendSpr = NA; self.pendCoolBar = NA
        self.provEdge = 0; self.provBar = NA; self.provPrice = NA; self.provTime = NA
        self.provEff = NA; self.provSpr = NA; self.provScore = 0
        self.exc = False; self.excTested = False; self.excBar = NA; self.excPrice = NA
        self.excTime = NA; self.excEff = NA; self.excSpr = NA; self.excScore = 0
        self.testTime = NA; self.testPrice = NA; self.testScore = 0
        self.strBar = NA; self.strTime = NA; self.strPrice = NA; self.strScore = 0
        self.lpsTime = NA; self.lpsPrice = NA; self.lpsBar = NA; self.lpsScore = 0
        self.entryTime = NA; self.entryPrice = NA; self.entryKind = 0
        self.outCount = 0; self.lastEventBar = NA; self.lastEventTime = NA; self.lastEventPrice = NA
        self.lastActBar = NA
        self.cfPrior = self.cfClimax = self.cfAR = self.cfST = self.cfExc = False
        self.cfTest = self.cfStrength = self.cfLPS = self.cfAccept = False


# ── funciones puras del Pine ──
def structure_confidence(prior, climax, ar, st, cDone, strength, lps, accept):
    return (10 if prior else 0) + (15 if climax else 0) + (10 if ar else 0) + (15 if st else 0) + \
        (15 if cDone else 0) + (15 if strength else 0) + (10 if lps else 0) + (10 if accept else 0)


def validation_score(trend, absorbed, rangeATR, st, opp, trav, clean, cause, terminal, strength, lps, accept):
    v = 0
    v += 10 if abs(trend) >= priorTrendStrong else 5 if abs(trend) >= priorTrendNeutral else 0
    v += 15 if absorbed else 0
    if phaseBRangeMinATR <= rangeATR <= phaseBRangeMaxATR:
        v += 10
    elif phaseBRangeMinATR * 0.75 <= rangeATR <= phaseBRangeMaxATR * 1.5:
        v += 5
    v += 15 if st >= minPhaseBTests else 8 if st >= 1 else 0
    v += 15 if (opp >= 1 and trav >= 2) else 8 if (opp >= 1 or trav >= 1) else 0
    v += 10 if clean else 0
    v += 10 if cause >= 3.0 else 5 if cause >= 1.5 else 0
    v += 10 if terminal else 0
    v += 3 if strength else 0
    v += 2 if lps else 0
    return min(v, 100)


def cause_units(trav, bAge, p, rangeATR):
    timeUnits = float(bAge) / max(float(p) * 6.0, 1.0)
    widthBonus = 0.5 if rangeATR >= phaseBRangeMinATR else 0.0
    return timeUnits + float(trav) * 0.5 + widthBonus


def test_class(near, holds, closeOK, e, sp, cE, cS):
    r = TEST_NONE
    if near:
        if not holds:
            r = TEST_FAILED
        elif closeOK and e <= cE * stMaxVolRatio and sp <= cS * stMaxSpreadRatio:
            r = TEST_GOOD
        else:
            r = TEST_POOR
    return r


def phaseA_min_bars(p):
    return max(phaseAMinBars, max(p, 1) * 2)


def phaseB_min_bars(p, rangeATR):
    p = max(p, 1)
    raw = int(pround(max(float(p * 6), rangeATR * float(p) * 1.00)))
    return max(minPhaseBBars, min(raw, minPhaseBBars * 2))


def phaseCD_min_bars(p):
    return max(phaseCToDMinBars, int(max(p, 1) / 2))


def phaseD_min_bars(p):
    return max(phaseDMinBars, max(p, 1))


def exc_recovery_limit(p):
    return max(excursionRecoveryBars, int(pround(max(p, 1) * 0.75)))


def phase_idle_limit(phase, hasAR, p):
    p = max(p, 1)
    if phase == PHASE_A:
        return max(phaseAAfterArMaxBars, p * 6) if hasAR else max(maxARBars, p * 4)
    if phase == PHASE_B:
        return max(phaseBIdleMaxBars, p * 20)
    if phase == PHASE_C:
        return max(phaseCIdleMaxBars, p * 8)
    if phase == PHASE_D:
        return max(phaseCIdleMaxBars * 2, p * 16)
    return NA


def phaseB_character_improving(n, effSum, sprSum, lastE, lastS):
    if n >= 2 and not na(lastE) and not na(lastS):
        avgE = effSum / n
        avgS = sprSum / n
        return lastE <= avgE and lastS <= avgS * 1.05
    return False


def robust_edge(e1, e2, e3, orig, isLow):
    med = NA
    if not na(e1) and not na(e2) and not na(e3):
        med = e1 + e2 + e3 - max(e1, e2, e3) - min(e1, e2, e3)
    elif not na(e1) and not na(e2):
        med = ((e1 + e2) / 2.0 + orig) / 2.0
    elif not na(e1):
        med = (e1 + orig) / 2.0
    if na(med):
        return orig
    return max(orig, med) if isLow else min(orig, med)


def type_from(stop, out, bull, bear):
    if out == DIR_ACCUM:
        return TYPE_REACCUM if (stop == DIR_DIST or bull) else TYPE_ACCUM
    if out == DIR_DIST:
        return TYPE_REDIST if (stop == DIR_ACCUM or bear) else TYPE_DIST
    return TYPE_NONE


def risk_plan(is_long, entry, rh, rl, exc, excP, teP, atr, sl_buffer_atr, tick):
    """Port de f_riskPlan: SL tras el extremo, TP1 = borde opuesto, TP2 = proyección de la altura."""
    hgt = max(rh - rl, tick)
    if is_long:
        ref = min(excP, rl) if (exc and not na(excP)) else (min(teP, rl) if not na(teP) else rl)
        sl = ref - atr * sl_buffer_atr
        risk = max(entry - sl, tick)
        tp1 = rh if entry < rh - atr * 0.25 else entry + risk
        tp2 = max(rh + hgt, tp1 + risk)
    else:
        ref = max(excP, rh) if (exc and not na(excP)) else (max(teP, rh) if not na(teP) else rh)
        sl = ref + atr * sl_buffer_atr
        risk = max(sl - entry, tick)
        tp1 = rl if entry > rl + atr * 0.25 else entry - risk
        tp2 = min(rl - hgt, tp1 - risk)
    rr2 = abs(tp2 - entry) / max(abs(entry - sl), tick)
    return sl, tp1, tp2, rr2


class Engine:
    def __init__(self, tick, tf_ms, strictness="standard"):
        self.tick = tick
        self.tf_ms = tf_ms
        self.strict = strictness
        self.i = -1
        self.T = []; self.O = []; self.H = []; self.L = []; self.C = []; self.V = []
        self.eff = []; self.spr = []; self.avgEffRaw = []; self.atrRaw = []; self.a = []
        self.liveLen = []; self.longSma = []; self.ph = []; self.pl = []
        self.dnEffc = []; self.upEffc = []; self.trs = []
        self.cumvol = 0.0
        self.s = WS()
        self.regime = REGIME_NONE; self.regimeBar = NA
        self.prelimBar = NA; self.prelimTime = NA; self.prelimPrice = NA
        self.prelimDir = DIR_NONE; self.prelimScore = 0
        self.lastPLBar = NA; self.lastPHBar = NA
        self.rs = [0] * 7
        self.lastResetWhy = -1
        self.last_t = 0

    # ── utilidades de series ──
    def _at(self, arr, k):
        j = self.i - k
        return arr[j] if 0 <= j < len(arr) else NA

    def _win(self, arr, n, k=0):
        end = self.i - k
        st = end - n + 1
        if st < 0 or end >= len(arr):
            return None
        return arr[st:end + 1]

    def _sma(self, arr, n, k=0):
        w = self._win(arr, n, k)
        return NA if w is None else sum(w) / n

    def _sum(self, arr, n, k=0):
        w = self._win(arr, n, k)
        return NA if w is None else sum(w)

    def _highest(self, arr, n, k=0):
        w = self._win(arr, n, k)
        return NA if w is None else max(w)

    def _lowest(self, arr, n, k=0):
        w = self._win(arr, n, k)
        return NA if w is None else min(w)

    def _pivot_high(self, L):
        i = self.i
        if L <= 0 or i - 2 * L < 0:
            return NA
        ci = i - L
        v = self.H[ci]
        for k in range(1, L + 1):
            if self.H[ci - k] >= v:
                return NA
        for k in range(1, L + 1):
            if self.H[ci + k] > v:
                return NA
        return v

    def _pivot_low(self, L):
        i = self.i
        if L <= 0 or i - 2 * L < 0:
            return NA
        ci = i - L
        v = self.L[ci]
        for k in range(1, L + 1):
            if self.L[ci - k] <= v:
                return NA
        for k in range(1, L + 1):
            if self.L[ci + k] < v:
                return NA
        return v

    def _prior_trend(self, n, endOff, a_now):
        n = max(n, 2)
        e = max(endOff, 0)
        cEnd = self._at(self.C, e)
        cStart = self._at(self.C, e + n)
        score = 0.0
        if not na(cEnd) and not na(cStart):
            unitA = max(nz(self._at(self.a, e), a_now), self.tick)
            net = cEnd - cStart
            disp = clamp(net / (unitA * math.sqrt(n)), -3.0, 3.0) * 15.0
            path = 0.0
            hh = ll = lh = hl = 0
            lastPH = NA
            lastPL = NA
            for k in range(n - 1, -1, -1):
                o = e + k
                c0 = nz(self._at(self.C, o))
                path += abs(c0 - nz(self._at(self.C, o + 1), c0))
                vph = self._at(self.ph, o)
                vpl = self._at(self.pl, o)
                if not na(vph):
                    if not na(lastPH):
                        hh += 1 if vph > lastPH else 0
                        lh += 1 if vph < lastPH else 0
                    lastPH = vph
                if not na(vpl):
                    if not na(lastPL):
                        hl += 1 if vpl > lastPL else 0
                        ll += 1 if vpl < lastPL else 0
                    lastPL = vpl
            er = abs(net) / path if path > 0 else 0.0
            erPart = (1.0 if net >= 0 else -1.0) * er * 25.0
            swings = hh + ll + lh + hl
            swingPart = float(hh + hl - lh - ll) / swings * 20.0 if swings > 0 else 0.0
            smaEnd = self._at(self.longSma, e)
            smaStart = self._at(self.longSma, e + n)
            smaPart = 0.0
            if not na(smaEnd) and not na(smaStart):
                smaPart = 10.0 if smaEnd > smaStart else -10.0 if smaEnd < smaStart else 0.0
            score = clamp(disp + erPart + swingPart + smaPart, -100.0, 100.0)
        return score

    # ── helpers de campaña (usan bar_index / time actuales) ──
    def _set_event(self, s, ev):
        s.ev = ev
        s.lastEventBar = self.i
        s.lastEventTime = self.t
        s.lastEventPrice = self.cl
        s.lastActBar = self.i

    def _bias_dir(self, s):
        if s.stopSide == DIR_ACCUM:
            return DIR_DIST if s.ctxBear else DIR_ACCUM
        if s.stopSide == DIR_DIST:
            return DIR_ACCUM if s.ctxBull else DIR_DIST
        return DIR_NONE

    def type_of(self, s):
        o = s.outcome if s.outcome != DIR_NONE else self._bias_dir(s)
        return TYPE_NONE if s.stopSide == DIR_NONE else type_from(s.stopSide, o, s.ctxBull, s.ctxBear)

    def _range_atr(self, s, a_now):
        if not na(s.rangeHigh) and not na(s.rangeLow):
            return abs(s.rangeHigh - s.rangeLow) / max(nz(s.climaxATR, a_now), self.tick)
        return 0.0

    def _hard_level(self, s, side):
        if side == DIR_ACCUM:
            if s.exc and s.outcome == DIR_ACCUM and not na(s.excPrice):
                return s.excPrice
            return s.rangeLow if na(s.origLow) else min(s.origLow, nz(s.rangeLow, s.origLow))
        if s.exc and s.outcome == DIR_DIST and not na(s.excPrice):
            return s.excPrice
        return s.rangeHigh if na(s.origHigh) else max(s.origHigh, nz(s.rangeHigh, s.origHigh))

    def _seed(self, s, side, score, pLen, trend, bull, bear, a_now, eff_now, spr_now):
        s.stopSide = side; s.phase = PHASE_A; s.startBar = self.i; s.pivLen = pLen
        s.birthTrend = trend; s.ctxBull = bull; s.ctxBear = bear
        s.climaxBar = self.i; s.climaxTime = self.t
        s.climaxPrice = self.lo if side == DIR_ACCUM else self.hi
        s.climaxEff = eff_now; s.climaxSpr = spr_now; s.climaxATR = a_now; s.climaxScore = score
        if side == DIR_ACCUM:
            s.origLow = self.lo; s.rangeLow = self.lo
        else:
            s.origHigh = self.hi; s.rangeHigh = self.hi
        s.cfPrior = True
        self._set_event(s, EV_SC if side == DIR_ACCUM else EV_BC)

    def _freeze_ar(self, s):
        s.arBar = s.arRunBar; s.arTime = s.arRunTime; s.arPrice = s.arRunPrice; s.cfAR = True
        if s.stopSide == DIR_ACCUM:
            s.origHigh = s.arRunPrice; s.rangeHigh = s.arRunPrice
        else:
            s.origLow = s.arRunPrice; s.rangeLow = s.arRunPrice

    @staticmethod
    def _tri_add(h, pb, t, price):
        if na(h.t1):
            h.b1, h.t1, h.p1 = pb, t, price
        elif na(h.t2) and pb > nz(h.b1, -1):
            h.b2, h.t2, h.p2 = pb, t, price
        elif na(h.t3) and pb > nz(h.b2, nz(h.b1, -1)):
            h.b3, h.t3, h.p3 = pb, t, price

    def _register_st(self, s, price, t, pb, e, sp, score):
        s.stCount += 1; s.stN += 1; s.stEffSum += e; s.stSprSum += sp
        s.lastGoodEff = e; s.lastGoodSpr = sp
        s.stBar = pb; s.stTime = t; s.stPrice = price
        self._tri_add(s.stHist, pb, t, price)
        s.stScore = score
        s.edge3 = s.edge2; s.edge2 = s.edge1; s.edge1 = price
        if s.stopSide == DIR_ACCUM:
            s.rangeLow = robust_edge(s.edge1, s.edge2, s.edge3, s.origLow, True)
        else:
            s.rangeHigh = robust_edge(s.edge1, s.edge2, s.edge3, s.origHigh, False)
        s.cfST = True
        self._set_event(s, EV_ST)

    def _register_opp(self, s, price, t, pb, e, sp):
        s.oppCount += 1; s.opN += 1; s.opEffSum += e; s.opSprSum += sp
        s.opLastBar = pb; s.opLastPrice = price
        self._tri_add(s.opHist, pb, t, price)
        s.lastActBar = self.i

    @staticmethod
    def _clear_terminal(s):
        s.exc = False; s.excTested = False; s.excBar = NA; s.excPrice = NA; s.excTime = NA
        s.excEff = NA; s.excSpr = NA; s.excScore = 0
        s.testTime = NA; s.testPrice = NA; s.testScore = 0
        s.cfExc = False; s.cfTest = False; s.cReadyBar = NA; s.cStartTime = NA

    def _exc_from_pend(self, s, score):
        s.exc = True; s.excTested = False
        s.excBar = s.pendExtBar; s.excPrice = s.pendExt; s.excTime = s.pendExtTime
        s.excEff = s.pendEff; s.excSpr = s.pendSpr; s.excScore = score
        s.cfExc = True; s.outcome = s.pendEdge; s.cStartTime = s.pendExtTime
        s.phase = PHASE_C; s.cReadyBar = NA; s.pend = False; s.provEdge = 0
        self._set_event(s, EV_SPRING if s.outcome == DIR_ACCUM else EV_UTAD)

    @staticmethod
    def _adopt_prov(s):
        s.exc = True; s.excTested = False
        s.excBar = s.provBar; s.excPrice = s.provPrice; s.excTime = s.provTime
        s.excEff = s.provEff; s.excSpr = s.provSpr; s.excScore = s.provScore
        s.cfExc = True; s.outcome = s.provEdge; s.cStartTime = s.provTime; s.provEdge = 0

    def _enter_ctest(self, s, outc, t, price, score):
        s.phase = PHASE_C; s.outcome = outc; s.cStartTime = t; s.cReadyBar = self.i
        s.testTime = t; s.testPrice = price; s.testScore = score
        s.cfTest = True; s.pend = False
        self._set_event(s, EV_CTEST_ACC if outc == DIR_ACCUM else EV_CTEST_DST)

    def _promote_d(self, s, outc, score, price):
        s.outcome = outc; s.phase = PHASE_D; s.dStartBar = self.i; s.dStartTime = self.t
        s.strBar = self.i; s.strTime = self.t; s.strPrice = price; s.strScore = score
        s.cfStrength = True; s.pend = False; s.outCount = 0
        self._set_event(s, EV_SOS if outc == DIR_ACCUM else EV_SOW)

    def _demote_to_b(self, s):
        self._clear_terminal(s)
        s.outcome = DIR_NONE; s.phase = PHASE_B
        s.strBar = NA; s.strTime = NA; s.strPrice = NA; s.strScore = 0
        s.lpsTime = NA; s.lpsPrice = NA; s.lpsBar = NA; s.lpsScore = 0
        s.dStartBar = NA; s.dStartTime = NA
        s.cfStrength = False; s.cfLPS = False
        s.provEdge = 0; s.pend = False; s.outCount = 0
        s.lastBadBar = self.i; s.lastActBar = self.i

    @staticmethod
    def _conf(s):
        cDone = s.cfTest or (s.cfExc and s.cfStrength)
        return structure_confidence(s.cfPrior, s.cfClimax, s.cfAR, s.cfST, cDone, s.cfStrength, s.cfLPS, s.cfAccept)

    def _validation(self, s, p, trend_now, a_now):
        if s.stopSide == DIR_NONE:
            return 0
        rATR = self._range_atr(s, a_now)
        bAge = max(self.i - s.bStartBar, 0) if not na(s.bStartBar) else 0
        badAge = -1 if na(s.lastBadBar) else self.i - s.lastBadBar
        clean = badAge < 0 or badAge >= int(pround(p * phaseBBadTestCooldownFactor))
        cause = cause_units(s.travCount, bAge, p, rATR)
        terminal = (s.cfTest and (not s.exc or s.excTested)) or (s.cfExc and s.cfStrength)
        return validation_score(nz(s.birthTrend, trend_now), s.absorbed, rATR, s.stCount, s.oppCount,
                                s.travCount, clean, cause, terminal, s.cfStrength, s.cfLPS, s.cfAccept)

    def _mature(self, s, p, a_now):
        rATR = self._range_atr(s, a_now)
        bAge = self.i - s.bStartBar if not na(s.bStartBar) else 0
        bMin = phaseB_min_bars(p, rATR)
        badAge = -1 if na(s.lastBadBar) else self.i - s.lastBadBar
        clean = badAge < 0 or badAge >= int(pround(p * phaseBBadTestCooldownFactor))
        opp = minPhaseBOppositeTests <= 0 or s.oppCount >= minPhaseBOppositeTests
        trav = minPhaseBTraversals <= 0 or s.travCount >= minPhaseBTraversals
        ch = phaseB_character_improving(s.stN, s.stEffSum, s.stSprSum, s.lastGoodEff, s.lastGoodSpr)
        support = (1 if opp else 0) + (1 if trav else 0) + (1 if clean else 0) + (1 if ch else 0)
        sane = phaseBRangeMinATR * 0.75 <= rATR <= phaseBRangeMaxATR * 2.0
        return s.phase == PHASE_B and bAge >= bMin and s.stCount >= minPhaseBTests and sane and support >= 2

    def _entry_readiness(self, s, minConf, valFloor, a_now):
        bull = s.outcome == DIR_ACCUM
        if na(s.rangeHigh) or na(s.rangeLow):
            distATR = 99.0
        elif bull:
            distATR = (self.cl - s.rangeHigh) / max(a_now, self.tick)
        else:
            distATR = (s.rangeLow - self.cl) / max(a_now, self.tick)
        ageBars = (self.t - s.lastEventTime) / max(float(self.tf_ms), 1.0) if not na(s.lastEventTime) else 999.0
        terminal = (s.exc and s.excTested) or (not s.exc and s.cfTest)
        conf = self._conf(s)
        r = 0
        r += 1 if s.outcome != DIR_NONE else 0
        r += 1 if s.phase >= PHASE_C else 0
        r += 1 if terminal else 0
        r += 1 if s.cfStrength else 0
        r += 1 if s.cfLPS else 0
        r += 1 if conf >= minConf else 0
        r += 1 if self._validation(s, nz(s.pivLen, pivotLen), s.birthTrend, a_now) >= valFloor else 0
        r += 1 if distATR <= 2.0 else 0
        r += 1 if ageBars <= 50.0 else 0
        return r

    # ───────────────── API ─────────────────
    def add_bar(self, c):
        """c = {t,o,h,l,c,v} vela CERRADA. Devuelve dict con eventos y estado."""
        self.i += 1
        i = self.i
        self.T.append(float(c["t"])); self.O.append(c["o"]); self.H.append(c["h"])
        self.L.append(c["l"]); self.C.append(c["c"]); self.V.append(c["v"])
        self.last_t = c["t"]
        h, l, cl, v = c["h"], c["l"], c["c"], c["v"]
        self.cumvol += v
        spr = max(h - l, self.tick)
        eff = spr if self.cumvol <= 0.0 else v
        self.spr.append(spr); self.eff.append(eff)
        self.avgEffRaw.append(self._sma(self.eff, volLen))
        pc = self.C[i - 1] if i > 0 else cl
        tr = (h - l) if i == 0 else max(h - l, abs(h - pc), abs(l - pc))
        self.trs.append(tr)
        if i < atrLen - 1:
            atr = NA
        elif i == atrLen - 1:
            atr = sum(self.trs[:atrLen]) / atrLen
        else:
            atr = (self.atrRaw[i - 1] * (atrLen - 1) + tr) / atrLen
        self.atrRaw.append(atr)
        a = nz(atr, spr)
        self.a.append(a)
        aBase = self._sma(self.a, adaptiveSwingVolLen)
        aRatio = a / aBase if nz(aBase) > 0.0 else 1.0
        self.liveLen.append(max(adaptiveSwingMin, min(adaptiveSwingMax, int(pround(pivotLen * aRatio)))))
        self.longSma.append(self._sma(self.C, continuationTrendLen))
        avgEff = nz(self.avgEffRaw[i], eff)
        relE = eff / max(avgEff, 1e-10)
        unit = max(a, self.tick)
        effort2 = max(relE, 0.01) * max(spr / unit, 0.01)
        self.dnEffc.append(max(nz(pc, cl) - cl, 0.0) / unit / effort2)
        self.upEffc.append(max(cl - nz(pc, cl), 0.0) / unit / effort2)
        return self._step()

    def _step(self):
        i = self.i
        s = self.s
        T, tick = self.T, self.tick
        t = self.t = T[i]
        op, hi, lo, cl = self.O[i], self.H[i], self.L[i], self.C[i]
        self.hi, self.lo, self.cl = hi, lo, cl
        eff, spr = self.eff[i], self.spr[i]
        avgEffRaw = self.avgEffRaw[i]
        avgEff = nz(avgEffRaw, eff)
        avgEffPrev = nz(self._at(self.avgEffRaw, 1), avgEff)
        atrRaw = self.atrRaw[i]
        a = self.a[i]
        aPrev = nz(self._at(self.atrRaw, 1), a)
        unit = max(a, tick)
        cPos = (cl - lo) / spr
        relE = eff / max(avgEff, 1e-10)
        sprATR = spr / unit
        recentEff = self._sma(self.eff, climaxAbsorptionMinBars)
        recentLow = self._lowest(self.L, climaxAbsorptionMinBars)
        recentHigh = self._highest(self.H, climaxAbsorptionMinBars)
        priorLo = self._lowest(self.L, extremeLen, 1)
        priorHi = self._highest(self.H, extremeLen, 1)
        effHiPrior = self._highest(self.eff, extremeLen, 1)
        newLow = (not na(priorLo)) and lo <= priorLo
        newHigh = (not na(priorHi)) and hi >= priorHi
        liveLen = self.liveLen[i]
        preLen = nz(self._at(self.liveLen, 3), liveLen)

        pLen = int(nz(s.pivLen, liveLen)) if s.phase != PHASE_NONE else liveLen
        ph = self._pivot_high(pLen)
        pl = self._pivot_low(pLen)
        self.ph.append(ph); self.pl.append(pl)
        pivBar = i - pLen
        pA = max(nz(self._at(self.atrRaw, pLen), a), tick)
        pEff = nz(self._at(self.eff, pLen), eff)
        pHigh = nz(self._at(self.H, pLen), hi)
        pLow = nz(self._at(self.L, pLen), lo)
        pSpr = max(pHigh - pLow, tick)
        pCPos = (nz(self._at(self.C, pLen), cl) - pLow) / pSpr
        pAvgEff = nz(self._at(self.avgEffRaw, pLen), avgEff)
        pTime = nz(self._at(T, pLen), t)

        longSma = self.longSma[i]
        trendBars = max(trendLen, min(priorTrendMaxBars, int(pround(liveLen * priorTrendPivotFactor))))
        trendEnd = max(2, min(8, int(pround(liveLen * 0.75))))
        trendScore = self._prior_trend(trendBars, trendEnd, a)
        downTrend = trendScore <= -priorTrendNeutral
        upTrend = trendScore >= priorTrendNeutral
        strongTrend = abs(trendScore) >= priorTrendStrong
        c1 = self._at(self.C, 1)
        lsm1 = self._at(self.longSma, 1)
        lsm20 = self._at(self.longSma, 20)
        longBull = nz(c1) > nz(lsm1) and nz(lsm1) > nz(lsm20)
        longBear = (not na(lsm20)) and nz(c1) < nz(lsm1) and nz(lsm1) < nz(lsm20)

        dnBase = self._sma(self.dnEffc, prelimEfficiencyLookback, 1)
        upBase = self._sma(self.upEffc, prelimEfficiencyLookback, 1)
        dnAbsorb = (not na(dnBase)) and self.dnEffc[i] <= dnBase * prelimEfficiencyRatio
        upAbsorb = (not na(upBase)) and self.upEffc[i] <= upBase * prelimEfficiencyRatio
        nearRecentLow = (not na(priorLo)) and lo <= priorLo + a * prelimExtremeATR
        nearRecentHigh = (not na(priorHi)) and hi >= priorHi - a * prelimExtremeATR

        hiCInv = self._highest(self.C, structureInvalidationBars)
        loCInv = self._lowest(self.C, structureInvalidationBars)
        hiCDep = self._highest(self.C, phaseBDepartureBars)
        loCDep = self._lowest(self.C, phaseBDepartureBars)
        hiCA = self._highest(self.C, phaseAPrematureDepartureBars)
        loCA = self._lowest(self.C, phaseAPrematureDepartureBars)
        hiCConf = self._highest(self.C, confirmBars)
        loCConf = self._lowest(self.C, confirmBars)
        hiCDir = self._highest(self.C, directAcceptanceBars)
        loCDir = self._lowest(self.C, directAcceptanceBars)
        hiCFail = self._highest(self.C, phaseDFailBars)
        loCFail = self._lowest(self.C, phaseDFailBars)
        mbLow = self._lowest(self.L, sosMultiBarLen)
        mbHigh = self._highest(self.H, sosMultiBarLen)
        mbSum = self._sum(self.eff, sosMultiBarLen)
        mbEffRatio = mbSum / max(avgEff * sosMultiBarLen, 1e-10) if not na(mbSum) else NA
        mbSOS = (cl - mbLow) / unit >= sosMultiBarATR and mbEffRatio >= sosMultiBarEffort and cPos >= 0.50
        mbSOW = (mbHigh - cl) / unit >= sosMultiBarATR and mbEffRatio >= sosMultiBarEffort and cPos <= 0.50
        c3 = nz(self._at(self.C, 3), cl)
        res3Up = max(cl - c3, 0.0) / unit
        res3Dn = max(c3 - cl, 0.0) / unit
        sosScore = (1 if relE >= strengthVolMult else 0) + (1 if sprATR >= strengthSpreadATR else 0) + \
            (1 if cPos >= sosCloseMin else 0) + (1 if (cl > op and cl - op >= a * 0.50) else 0)
        sowScore = (1 if relE >= strengthVolMult else 0) + (1 if sprATR >= strengthSpreadATR else 0) + \
            (1 if cPos <= sowCloseMax else 0) + (1 if (cl < op and op - cl >= a * 0.50) else 0)
        close1 = nz(self._at(self.C, 1), cl)
        close2 = nz(self._at(self.C, 2), cl)
        ctxBars = max(priorTrendMaxBars, continuationTrendLen) * 2
        sig = 0

        # ================= bloque commit =================
        p0 = int(nz(s.pivLen, liveLen))
        rk0 = (not na(s.rangeHigh)) and (not na(s.rangeLow))
        rH0, rL0 = s.rangeHigh, s.rangeLow
        rHt0 = max(rH0 - rL0, tick) if rk0 else NA
        rMid0 = (rH0 + rL0) / 2.0 if rk0 else NA
        probeOpen = s.pend and (i - s.pendStartBar <= exc_recovery_limit(p0))
        structAge = i - s.startBar if not na(s.startBar) else 0
        ageOKBull = self.regime != REGIME_MARKDOWN or structAge >= oppositeCycleMinBars
        ageOKBear = self.regime != REGIME_MARKUP or structAge >= oppositeCycleMinBars
        hardBull0 = self._hard_level(s, DIR_ACCUM)
        hardBear0 = self._hard_level(s, DIR_DIST)
        resetWhy = -1

        if s.phase == PHASE_A:
            aAge = i - s.climaxBar
            aInvAcc = s.stopSide == DIR_ACCUM and hiCInv < s.climaxPrice - a * structureInvalidationATR
            aInvDst = s.stopSide == DIR_DIST and loCInv > s.climaxPrice + a * structureInvalidationATR
            aAbsorbExp = (not s.absorbed) and aAge > climaxAbsorptionMaxBars
            aNoAR = (not s.arOK) and aAge > maxARBars
            aOverExt = s.arOK and (not na(s.arRunPrice)) and \
                abs(s.arRunPrice - s.climaxPrice) / max(nz(s.climaxATR, a), tick) > arMaxExtensionATR
            aBuf = max(rHt0 * phaseAPrematureDepartureTRFrac, a * phaseAPrematureDepartureATR) if rk0 else NA
            aDepart = aAge > maxARBars and rk0 and (
                (s.stopSide == DIR_ACCUM and loCA > rH0 + aBuf) or (s.stopSide == DIR_DIST and hiCA < rL0 - aBuf))
            if aInvAcc or aInvDst:
                resetWhy = RS_INVALID
            elif aAbsorbExp:
                resetWhy = RS_ABSORB
            elif aNoAR or aOverExt or aDepart:
                resetWhy = RS_NORANGE

        if s.phase == PHASE_C and not probeOpen and resetWhy < 0:
            if s.outcome == DIR_ACCUM and (not na(hardBull0)) and hiCInv < hardBull0 - a * structureInvalidationATR:
                resetWhy = RS_INVALID
            elif s.outcome == DIR_DIST and (not na(hardBear0)) and loCInv > hardBear0 + a * structureInvalidationATR:
                resetWhy = RS_INVALID

        if s.phase == PHASE_D and rk0 and resetWhy < 0:
            if s.outcome == DIR_ACCUM:
                if (not na(hardBull0)) and hiCInv < hardBull0 - a * structureInvalidationATR:
                    resetWhy = RS_INVALID
                elif hiCFail < rMid0:
                    self._demote_to_b(s); self.rs[RS_DEMOTE] += 1
            elif s.outcome == DIR_DIST:
                if (not na(hardBear0)) and loCInv > hardBear0 + a * structureInvalidationATR:
                    resetWhy = RS_INVALID
                elif loCFail > rMid0:
                    self._demote_to_b(s); self.rs[RS_DEMOTE] += 1

        if s.phase == PHASE_E and rk0 and resetWhy < 0:
            eFail = (hiCFail < rMid0) if s.outcome == DIR_ACCUM else (loCFail > rMid0)
            eOld = phaseEMaxBars > 0 and (not na(s.eStartBar)) and i - s.eStartBar > phaseEMaxBars
            if eFail or eOld:
                resetWhy = RS_EEND

        idleLim = phase_idle_limit(s.phase, s.arOK, p0)
        if resetWhy < 0 and not probeOpen and (not na(idleLim)) and (not na(s.lastActBar)) and i - s.lastActBar > idleLim:
            resetWhy = RS_STALE

        if resetWhy >= 0:
            self.rs[resetWhy] += 1
            self.lastResetWhy = resetWhy
            s = self.s = WS()

        # preliminar
        if s.phase == PHASE_NONE or s.phase == PHASE_E:
            psSc = (1 if downTrend else 0) + (1 if nearRecentLow else 0) + (1 if relE >= prelimVolMult else 0) + \
                (1 if sprATR >= 0.80 else 0) + (1 if cPos >= 0.45 else 0) + (1 if dnAbsorb else 0)
            psySc = (1 if upTrend else 0) + (1 if nearRecentHigh else 0) + (1 if relE >= prelimVolMult else 0) + \
                (1 if sprATR >= 0.80 else 0) + (1 if cPos <= 0.55 else 0) + (1 if upAbsorb else 0)
            psStale = na(self.prelimBar) or i - self.prelimBar > extremeLen
            if downTrend and nearRecentLow and relE >= prelimVolMult and psSc >= prelimMinScore and \
                    (self.prelimDir != DIR_ACCUM or psStale or psSc >= self.prelimScore):
                self.prelimBar, self.prelimTime, self.prelimPrice = i, t, lo
                self.prelimDir, self.prelimScore = DIR_ACCUM, psSc
            elif upTrend and nearRecentHigh and relE >= prelimVolMult and psySc >= prelimMinScore and \
                    (self.prelimDir != DIR_DIST or psStale or psySc >= self.prelimScore):
                self.prelimBar, self.prelimTime, self.prelimPrice = i, t, hi
                self.prelimDir, self.prelimScore = DIR_DIST, psySc

        # clímax
        relaxK = relaxedClimaxFactor if strongTrend else 1.0
        volHit = eff >= avgEffPrev * climaxVolMult * relaxK
        sprHit = spr >= aPrev * climaxSpreadMult * relaxK
        exceptional = ((not na(effHiPrior)) and eff >= effHiPrior) or spr >= aPrev * climaxSpreadMult * 1.5
        scSc = (1 if downTrend else 0) + (1 if newLow else 0) + (1 if volHit else 0) + (1 if sprHit else 0) + \
            (1 if cPos >= scCloseMin else 0) + (1 if exceptional else 0)
        bcSc = (1 if upTrend else 0) + (1 if newHigh else 0) + (1 if volHit else 0) + (1 if sprHit else 0) + \
            (1 if cPos <= bcCloseMax else 0) + (1 if exceptional else 0)
        seedOpen = s.phase == PHASE_NONE or s.phase == PHASE_E
        canSC = seedOpen or (s.phase == PHASE_A and s.stopSide == DIR_ACCUM and lo < s.climaxPrice)
        canBC = seedOpen or (s.phase == PHASE_A and s.stopSide == DIR_DIST and hi > s.climaxPrice)
        isSC = canSC and downTrend and newLow and volHit and sprHit and scSc >= climaxMinScore
        isBC = canBC and upTrend and newHigh and volHit and sprHit and bcSc >= climaxMinScore
        if isSC != isBC:
            seedSide = DIR_ACCUM if isSC else DIR_DIST
            recentMarkup = self.regime == REGIME_MARKUP and (not na(self.regimeBar)) and i - self.regimeBar <= ctxBars
            recentMarkdown = self.regime == REGIME_MARKDOWN and (not na(self.regimeBar)) and i - self.regimeBar <= ctxBars
            s = self.s = WS()
            self._seed(s, seedSide, scSc if isSC else bcSc, preLen, trendScore,
                       recentMarkup or longBull, recentMarkdown or longBear, a, eff, spr)
            if self.prelimDir == seedSide and (not na(self.prelimBar)) and self.prelimBar < i and i - self.prelimBar <= extremeLen:
                s.psTime, s.psPrice, s.psScore = self.prelimTime, self.prelimPrice, self.prelimScore

        # absorción del clímax
        if s.phase == PHASE_A and (not s.absorbed) and (not na(s.climaxBar)):
            absAge = i - s.climaxBar
            if climaxAbsorptionMinBars <= absAge <= climaxAbsorptionMaxBars:
                effortOK = recentEff >= avgEff * climaxAbsorptionVolFloor
                accAbs = s.stopSide == DIR_ACCUM and recentLow >= s.climaxPrice - s.climaxATR * climaxAbsorptionExtremeATR \
                    and cl >= s.climaxPrice + s.climaxATR * climaxAbsorptionReboundATR
                dstAbs = s.stopSide == DIR_DIST and recentHigh <= s.climaxPrice + s.climaxATR * climaxAbsorptionExtremeATR \
                    and cl <= s.climaxPrice - s.climaxATR * climaxAbsorptionReboundATR
                if effortOK and (accAbs or dstAbs):
                    s.absorbed = True; s.cfClimax = True; s.lastActBar = i
                    sig |= BIT_SC if s.stopSide == DIR_ACCUM else BIT_BC
                    if not na(s.psTime):
                        sig |= BIT_PS

        # AR
        if s.phase == PHASE_A and na(s.arBar) and (not na(s.climaxBar)) and i > s.climaxBar and i - s.climaxBar <= maxARBars:
            if s.stopSide == DIR_ACCUM:
                if na(s.arRunPrice) or hi > s.arRunPrice:
                    s.arRunPrice, s.arRunBar, s.arRunTime = hi, i, t
                s.arOK = s.arOK or (s.arRunPrice - s.climaxPrice >= a * minARATR)
            else:
                if na(s.arRunPrice) or lo < s.arRunPrice:
                    s.arRunPrice, s.arRunBar, s.arRunTime = lo, i, t
                s.arOK = s.arOK or (s.climaxPrice - s.arRunPrice >= a * minARATR)
        if s.phase == PHASE_A and s.arOK and s.absorbed and na(s.arBar):
            if s.stopSide == DIR_ACCUM:
                s.rangeHigh = s.arRunPrice; s.origHigh = s.arRunPrice
            else:
                s.rangeLow = s.arRunPrice; s.origLow = s.arRunPrice

        p1 = int(nz(s.pivLen, liveLen))
        rk1 = (not na(s.rangeHigh)) and (not na(s.rangeLow))
        rH1, rL1 = s.rangeHigh, s.rangeLow
        origHt1 = max(nz(s.origHigh, rH1) - nz(s.origLow, rL1), tick) if rk1 else NA
        mature1 = self._mature(s, p1, a)
        newPL = (not na(pl)) and (na(self.lastPLBar) or pivBar > self.lastPLBar)
        newPH = (not na(ph)) and (na(self.lastPHBar) or pivBar > self.lastPHBar)
        if newPL:
            self.lastPLBar = pivBar
        if newPH:
            self.lastPHBar = pivBar
        plUsed = phUsed = False

        # tests terminales (variante sin Spring/UTAD)
        if newPL and s.phase == PHASE_B and mature1 and rk1:
            loRefST = s.stopSide == DIR_ACCUM
            tN = s.stN if loRefST else s.opN
            tBar = s.stBar if loRefST else s.opLastBar
            tPrice = s.stPrice if loRefST else s.opLastPrice
            if tN > 0 and not na(tBar):
                tE = (s.stEffSum if loRefST else s.opEffSum) / tN
                tS = (s.stSprSum if loRefST else s.opSprSum) / tN
                tLater = pivBar >= tBar + terminalTestMinBarsAfterST
                tNear = pl <= rL1 + pA * testTolATR
                tHolds = pl >= min(nz(s.origLow, rL1), rL1) - pA * testExtremeToleranceATR
                tHigher = na(tPrice) or pl >= tPrice - pA * testExtremeToleranceATR
                tqV = pEff <= tE * terminalTestVolRatio
                tqS = pSpr <= tS * terminalTestSpreadRatio
                tnV = pEff <= tE * terminalTestOtherMaxRatio
                tnS = pSpr <= tS * terminalTestOtherMaxRatio
                tSc = (1 if tqV else 0) + (1 if tqS else 0) + (1 if pCPos >= 0.50 else 0)
                if tLater and tNear and tHolds and tHigher and ((tqV and tnS) or (tqS and tnV)) and tSc >= testMinScore:
                    self._enter_ctest(s, DIR_ACCUM, pTime, pl, tSc)
                    sig |= BIT_CTEST; plUsed = True
        if newPH and s.phase == PHASE_B and mature1 and rk1:
            hiRefST = s.stopSide == DIR_DIST
            uN = s.stN if hiRefST else s.opN
            uBar = s.stBar if hiRefST else s.opLastBar
            uPrice = s.stPrice if hiRefST else s.opLastPrice
            if uN > 0 and not na(uBar):
                uE = (s.stEffSum if hiRefST else s.opEffSum) / uN
                uS = (s.stSprSum if hiRefST else s.opSprSum) / uN
                uLater = pivBar >= uBar + terminalTestMinBarsAfterST
                uNear = ph >= rH1 - pA * testTolATR
                uHolds = ph <= max(nz(s.origHigh, rH1), rH1) + pA * testExtremeToleranceATR
                uLower = na(uPrice) or ph <= uPrice + pA * testExtremeToleranceATR
                uqV = pEff <= uE * terminalTestVolRatio
                uqS = pSpr <= uS * terminalTestSpreadRatio
                unV = pEff <= uE * terminalTestOtherMaxRatio
                unS = pSpr <= uS * terminalTestOtherMaxRatio
                uSc = (1 if uqV else 0) + (1 if uqS else 0) + (1 if pCPos <= 0.50 else 0)
                if uLater and uNear and uHolds and uLower and ((uqV and unS) or (uqS and unV)) and uSc >= testMinScore:
                    self._enter_ctest(s, DIR_DIST, pTime, ph, uSc)
                    sig |= BIT_CTEST; phUsed = True

        # primer ST (Fase A -> B)
        if newPL and not plUsed and s.phase == PHASE_A and s.stopSide == DIR_ACCUM and s.absorbed and s.arOK \
                and (not na(s.arRunBar)) and pivBar > s.arRunBar:
            aZoneTop = s.origLow + (s.arRunPrice - s.origLow) * phaseBZoneFrac
            aNearL = abs(pl - s.origLow) <= pA * boundaryTolATR or pl <= aZoneTop
            aHoldsL = pl >= s.origLow - pA * boundaryTolATR
            aCloseL = pCPos >= 0.45
            aTcL = test_class(aNearL, aHoldsL, aCloseL, pEff, pSpr, s.climaxEff, s.climaxSpr)
            aScL = (1 if aNearL else 0) + (1 if pEff <= s.climaxEff * stMaxVolRatio else 0) + \
                (1 if pSpr <= s.climaxSpr * stMaxSpreadRatio else 0) + (1 if aHoldsL else 0) + (1 if aCloseL else 0) + 1
            aAgeL = pivBar - s.startBar >= phaseA_min_bars(p1)
            aSpaceL = pivBar - s.arRunBar >= max(2, p1)
            if aNearL:
                s.lastActBar = i
            if aTcL == TEST_GOOD and aScL >= stMinScore and aAgeL and aSpaceL:
                self._freeze_ar(s)
                self._register_st(s, pl, pTime, pivBar, pEff, pSpr, aScL)
                s.phase = PHASE_B; s.bStartBar = pivBar; s.bStartTime = pTime
                sig |= BIT_AR | BIT_ST; plUsed = True
        if newPH and not phUsed and s.phase == PHASE_A and s.stopSide == DIR_DIST and s.absorbed and s.arOK \
                and (not na(s.arRunBar)) and pivBar > s.arRunBar:
            aZoneBot = s.origHigh - (s.origHigh - s.arRunPrice) * phaseBZoneFrac
            aNearH = abs(ph - s.origHigh) <= pA * boundaryTolATR or ph >= aZoneBot
            aHoldsH = ph <= s.origHigh + pA * boundaryTolATR
            aCloseH = pCPos <= 0.55
            aTcH = test_class(aNearH, aHoldsH, aCloseH, pEff, pSpr, s.climaxEff, s.climaxSpr)
            aScH = (1 if aNearH else 0) + (1 if pEff <= s.climaxEff * stMaxVolRatio else 0) + \
                (1 if pSpr <= s.climaxSpr * stMaxSpreadRatio else 0) + (1 if aHoldsH else 0) + (1 if aCloseH else 0) + 1
            aAgeH = pivBar - s.startBar >= phaseA_min_bars(p1)
            aSpaceH = pivBar - s.arRunBar >= max(2, p1)
            if aNearH:
                s.lastActBar = i
            if aTcH == TEST_GOOD and aScH >= stMinScore and aAgeH and aSpaceH:
                self._freeze_ar(s)
                self._register_st(s, ph, pTime, pivBar, pEff, pSpr, aScH)
                s.phase = PHASE_B; s.bStartBar = pivBar; s.bStartTime = pTime
                sig |= BIT_AR | BIT_ST; phUsed = True

        # tests / pruebas de Fase B
        rk1 = (not na(s.rangeHigh)) and (not na(s.rangeLow))
        if newPL and not plUsed and s.phase == PHASE_B and rk1 and pivBar > s.bStartBar:
            bHt = max(s.rangeHigh - s.rangeLow, tick)
            if s.stopSide == DIR_ACCUM:
                bNear = abs(pl - s.rangeLow) <= pA * boundaryTolATR or abs(pl - s.origLow) <= pA * boundaryTolATR \
                    or pl <= s.rangeLow + bHt * phaseBZoneFrac
                bHolds = pl >= s.origLow - pA * boundaryTolATR
                bClose = pCPos >= 0.45
                bTc = test_class(bNear, bHolds, bClose, pEff, pSpr, s.climaxEff, s.climaxSpr)
                bSc = (1 if bNear else 0) + (1 if pEff <= s.climaxEff * stMaxVolRatio else 0) + \
                    (1 if pSpr <= s.climaxSpr * stMaxSpreadRatio else 0) + (1 if bHolds else 0) + (1 if bClose else 0) + 1
                bIsProv = s.provEdge == DIR_ACCUM and (not na(s.provBar)) and abs(pivBar - s.provBar) <= p1
                if bNear:
                    s.lastActBar = i
                if bTc == TEST_FAILED and not bIsProv:
                    s.lastBadBar = pivBar
                elif bTc == TEST_GOOD and bSc >= stMinScore:
                    self._register_st(s, pl, pTime, pivBar, pEff, pSpr, bSc)
                    sig |= BIT_ST
            else:
                if pl < s.rangeLow and pl >= nz(s.origLow, s.rangeLow) - origHt1 * phaseBEdgeExpansionCap:
                    s.rangeLow = pl
                oHtL = max(s.rangeHigh - s.rangeLow, tick)
                oNearL = pl <= s.rangeLow + pA * boundaryTolATR or pl <= s.rangeLow + oHtL * phaseBZoneFrac
                oInsideL = pl >= nz(s.origLow, s.rangeLow) - origHt1 * phaseBEdgeExpansionCap
                oCtrlL = pEff <= s.climaxEff * 1.20 and pSpr <= s.climaxSpr * 1.20
                if oNearL and oInsideL and oCtrlL and (na(s.opLastBar) or pivBar > s.opLastBar):
                    self._register_opp(s, pl, pTime, pivBar, pEff, pSpr)
        if newPH and not phUsed and s.phase == PHASE_B and rk1 and pivBar > s.bStartBar:
            bHtH = max(s.rangeHigh - s.rangeLow, tick)
            if s.stopSide == DIR_DIST:
                hNear = abs(ph - s.rangeHigh) <= pA * boundaryTolATR or abs(ph - s.origHigh) <= pA * boundaryTolATR \
                    or ph >= s.rangeHigh - bHtH * phaseBZoneFrac
                hHolds = ph <= s.origHigh + pA * boundaryTolATR
                hClose = pCPos <= 0.55
                hTc = test_class(hNear, hHolds, hClose, pEff, pSpr, s.climaxEff, s.climaxSpr)
                hSc = (1 if hNear else 0) + (1 if pEff <= s.climaxEff * stMaxVolRatio else 0) + \
                    (1 if pSpr <= s.climaxSpr * stMaxSpreadRatio else 0) + (1 if hHolds else 0) + (1 if hClose else 0) + 1
                hIsProv = s.provEdge == DIR_DIST and (not na(s.provBar)) and abs(pivBar - s.provBar) <= p1
                if hNear:
                    s.lastActBar = i
                if hTc == TEST_FAILED and not hIsProv:
                    s.lastBadBar = pivBar
                elif hTc == TEST_GOOD and hSc >= stMinScore:
                    self._register_st(s, ph, pTime, pivBar, pEff, pSpr, hSc)
                    sig |= BIT_ST
            else:
                if ph > s.rangeHigh and ph <= nz(s.origHigh, s.rangeHigh) + origHt1 * phaseBEdgeExpansionCap:
                    s.rangeHigh = ph
                oHtH = max(s.rangeHigh - s.rangeLow, tick)
                oNearH = ph >= s.rangeHigh - pA * boundaryTolATR or ph >= s.rangeHigh - oHtH * phaseBZoneFrac
                oInsideH = ph <= nz(s.origHigh, s.rangeHigh) + origHt1 * phaseBEdgeExpansionCap
                oCtrlH = pEff <= s.climaxEff * 1.20 and pSpr <= s.climaxSpr * 1.20
                if oNearH and oInsideH and oCtrlH and (na(s.opLastBar) or pivBar > s.opLastBar):
                    self._register_opp(s, ph, pTime, pivBar, pEff, pSpr)

        # cruces del rango
        if s.phase == PHASE_B and (not na(s.rangeHigh)) and (not na(s.rangeLow)):
            tvHt = max(s.rangeHigh - s.rangeLow, tick)
            loZoneP = newPL and pl <= s.rangeLow + tvHt * phaseBZoneFrac
            hiZoneP = newPH and ph >= s.rangeHigh - tvHt * phaseBZoneFrac
            zoneNow = (-1 if loZoneP else 1) if (loZoneP != hiZoneP) else 0
            if zoneNow != 0 and (na(s.lastZoneBar) or pivBar > s.lastZoneBar):
                if s.lastZone != 0 and zoneNow != s.lastZone:
                    s.travCount += 1; s.lastActBar = i
                s.lastZone = zoneNow; s.lastZoneBar = pivBar

        # test posterior al Spring / UTAD
        if newPL and s.phase == PHASE_C and s.outcome == DIR_ACCUM and s.exc and (not s.excTested) \
                and pivBar > s.excBar and (not na(s.rangeLow)):
            xNearL = pl <= s.rangeLow + pA * testTolATR
            xKeepL = pl >= s.excPrice - pA * testExtremeToleranceATR
            xScL = (1 if pEff <= s.excEff * testMaxVolRatio else 0) + (1 if pSpr <= s.excSpr * testMaxSpreadRatio else 0) + \
                (1 if pCPos >= 0.50 else 0)
            if xNearL and xKeepL and xScL >= testMinScore:
                s.excTested = True; s.cReadyBar = i; s.testTime = pTime; s.testPrice = pl; s.testScore = xScL
                s.cfTest = True
                self._set_event(s, EV_TEST); sig |= BIT_TEST
        if newPH and s.phase == PHASE_C and s.outcome == DIR_DIST and s.exc and (not s.excTested) \
                and pivBar > s.excBar and (not na(s.rangeHigh)):
            xNearH = ph >= s.rangeHigh - pA * testTolATR
            xKeepH = ph <= s.excPrice + pA * testExtremeToleranceATR
            xScH = (1 if pEff <= s.excEff * testMaxVolRatio else 0) + (1 if pSpr <= s.excSpr * testMaxSpreadRatio else 0) + \
                (1 if pCPos <= 0.50 else 0)
            if xNearH and xKeepH and xScH >= testMinScore:
                s.excTested = True; s.cReadyBar = i; s.testTime = pTime; s.testPrice = ph; s.testScore = xScH
                s.cfTest = True
                self._set_event(s, EV_TEST); sig |= BIT_TEST

        # LPS / LPSY
        if newPL and s.phase == PHASE_D and s.outcome == DIR_ACCUM and (not na(s.strBar)) and pivBar > s.strBar \
                and (not na(s.rangeHigh)):
            lHard = self._hard_level(s, DIR_ACCUM)
            lSide = (not na(lHard)) and pl > lHard - pA * testExtremeToleranceATR
            lCreek = pl >= s.rangeHigh - pA * lpsBoundaryATR
            lSc = (1 if pEff <= pAvgEff * lpsVolMult else 0) + (1 if pSpr <= pA * lpsSpreadATR else 0) + (1 if pCPos >= 0.45 else 0)
            if lSide and lCreek and lSc >= lpsMinScore:
                s.lpsTime = pTime; s.lpsPrice = pl; s.lpsBar = i; s.lpsScore = lSc; s.cfLPS = True
                self._set_event(s, EV_LPS); sig |= BIT_LPS
        if newPH and s.phase == PHASE_D and s.outcome == DIR_DIST and (not na(s.strBar)) and pivBar > s.strBar \
                and (not na(s.rangeLow)):
            yHard = self._hard_level(s, DIR_DIST)
            ySide = (not na(yHard)) and ph < yHard + pA * testExtremeToleranceATR
            yIce = ph <= s.rangeLow + pA * lpsBoundaryATR
            ySc = (1 if pEff <= pAvgEff * lpsVolMult else 0) + (1 if pSpr <= pA * lpsSpreadATR else 0) + (1 if pCPos <= 0.55 else 0)
            if ySide and yIce and ySc >= lpsMinScore:
                s.lpsTime = pTime; s.lpsPrice = ph; s.lpsBar = i; s.lpsScore = ySc; s.cfLPS = True
                self._set_event(s, EV_LPSY); sig |= BIT_LPSY

        p2 = int(nz(s.pivLen, liveLen))
        rk2 = (not na(s.rangeHigh)) and (not na(s.rangeLow))
        rH2, rL2 = s.rangeHigh, s.rangeLow
        recLimit2 = exc_recovery_limit(p2)
        mature2 = self._mature(s, p2, a)
        bAge2 = i - s.bStartBar if not na(s.bStartBar) else 0

        # Spring / UTAD
        probeB = s.phase == PHASE_B and s.stCount >= 1 and bAge2 >= max(3, p2 * 2)
        probeCLo = s.phase == PHASE_C and s.outcome == DIR_ACCUM and not s.exc
        probeCHi = s.phase == PHASE_C and s.outcome == DIR_DIST and not s.exc
        if rk2 and not s.pend and (na(s.pendCoolBar) or i > s.pendCoolBar):
            penLo = rL2 - lo
            penHi = hi - rH2
            okLo = (probeB or probeCLo) and penLo >= a * springMinPenATR and penLo <= a * springMaxPenATR
            okHi = (probeB or probeCHi) and penHi >= a * springMinPenATR and penHi <= a * springMaxPenATR
            if okLo != okHi:
                s.pend = True
                s.pendEdge = DIR_ACCUM if okLo else DIR_DIST
                s.pendStartBar = i; s.pendExtBar = i
                s.pendExt = lo if okLo else hi
                s.pendExtTime = t; s.pendEff = eff; s.pendSpr = spr
        if s.pend and rk2 and (s.phase == PHASE_B or s.phase == PHASE_C):
            if s.pendEdge == DIR_ACCUM and lo < s.pendExt:
                s.pendExt = lo; s.pendExtBar = i; s.pendExtTime = t
                s.pendEff = max(nz(s.pendEff), eff); s.pendSpr = max(nz(s.pendSpr), spr)
            elif s.pendEdge == DIR_DIST and hi > s.pendExt:
                s.pendExt = hi; s.pendExtBar = i; s.pendExtTime = t
                s.pendEff = max(nz(s.pendEff), eff); s.pendSpr = max(nz(s.pendSpr), spr)
            recAge = i - s.pendStartBar
            recovered = (cl > rL2) if s.pendEdge == DIR_ACCUM else (cl < rH2)
            depth = (rL2 - s.pendExt) if s.pendEdge == DIR_ACCUM else (s.pendExt - rH2)
            depthOK = a * springMinPenATR <= depth <= a * springMaxPenATR
            if s.pendEdge == DIR_ACCUM:
                recSc = (1 if cPos >= springCloseMin else 0) + (1 if eff <= avgEff * springEffortMaxMult else 0) + \
                    (1 if cl > op else 0) + (1 if spr >= a * 0.50 else 0)
            else:
                recSc = (1 if cPos <= utadCloseMax else 0) + (1 if eff <= avgEff * springEffortMaxMult else 0) + \
                    (1 if cl < op else 0) + (1 if spr >= a * 0.50 else 0)
            if recovered and depthOK and recAge <= recLimit2 and recSc >= excursionMinScore:
                probeEdge = s.pendEdge
                if s.phase == PHASE_B and not mature2:
                    s.provEdge = probeEdge; s.provBar = s.pendExtBar; s.provPrice = s.pendExt
                    s.provTime = s.pendExtTime; s.provEff = s.pendEff; s.provSpr = s.pendSpr
                    s.provScore = recSc; s.lastActBar = i; s.pend = False
                else:
                    if s.phase == PHASE_C:
                        self._clear_terminal(s)
                    self._exc_from_pend(s, recSc)
                    sig |= BIT_SPRING if probeEdge == DIR_ACCUM else BIT_UTAD
            elif recAge > recLimit2 or (not depthOK and depth > a * springMaxPenATR):
                if s.phase == PHASE_B:
                    s.lastBadBar = i
                s.pend = False
                s.pendCoolBar = i + p2

        if s.phase == PHASE_C and s.exc and (not s.excTested) and rk2:
            if s.outcome == DIR_ACCUM and lo < s.excPrice and lo >= rL2 - a * springMaxPenATR:
                s.excPrice = lo; s.excBar = i; s.excTime = t
                s.excEff = max(nz(s.excEff), eff); s.excSpr = max(nz(s.excSpr), spr)
            elif s.outcome == DIR_DIST and hi > s.excPrice and hi <= rH2 + a * springMaxPenATR:
                s.excPrice = hi; s.excBar = i; s.excTime = t
                s.excEff = max(nz(s.excEff), eff); s.excSpr = max(nz(s.excSpr), spr)

        # SOS / SOW (C -> D)
        if s.phase == PHASE_C and rk2 and not s.pend:
            cMinD = phaseCD_min_bars(p2)
            cFormal = (not s.exc) or s.excTested
            cAnchor = s.cReadyBar if not na(s.cReadyBar) else s.excBar
            cAgeReady = (not na(cAnchor)) and i - cAnchor >= cMinD
            cVal = self._validation(s, p2, trendScore, a)
            cValD = cVal if cFormal else min(100, cVal + 13)
            cConf = self._conf(s)
            cConfD = cConf if cFormal else min(100, cConf + 30)
            cHt = max(rH2 - rL2, tick)
            if cAgeReady and cValD >= phaseDValidationMin and cConfD >= minConfidencePhaseC:
                if s.outcome == DIR_ACCUM and ageOKBull:
                    domUp = rL2 + cHt * phaseDDominanceFrac
                    brkUp = cl > rH2 + a * breakATR
                    domOKUp = brkUp or ((cl >= domUp and close1 >= domUp) if cFormal else
                                        (cl >= domUp and close1 >= domUp and close2 >= domUp))
                    reqUp = strengthMinScore if cFormal else max(2, strengthMinScore - 1)
                    qUp = sosScore >= reqUp or mbSOS or ((not cFormal) and res3Up >= 1.0)
                    if domOKUp and qUp:
                        self._promote_d(s, DIR_ACCUM, sosScore, hi)
                        sig |= BIT_SOS
                elif s.outcome == DIR_DIST and ageOKBear:
                    domDn = rH2 - cHt * phaseDDominanceFrac
                    brkDn = cl < rL2 - a * breakATR
                    domOKDn = brkDn or ((cl <= domDn and close1 <= domDn) if cFormal else
                                        (cl <= domDn and close1 <= domDn and close2 <= domDn))
                    reqDn = strengthMinScore if cFormal else max(2, strengthMinScore - 1)
                    qDn = sowScore >= reqDn or mbSOW or ((not cFormal) and res3Dn >= 1.0)
                    if domOKDn and qDn:
                        self._promote_d(s, DIR_DIST, sowScore, lo)
                        sig |= BIT_SOW

        # salida de Fase B sin pasar por C (Spring provisional + ruptura)
        resetLate = -1
        if s.phase == PHASE_B and rk2 and not s.pend:
            dHt = max(rH2 - rL2, tick)
            dBuf = max(dHt * phaseBDepartureTRFrac, a * phaseBDepartureATR)
            upAcc = cl > rH2 + a * breakATR and close1 > rH2 + a * breakATR
            dnAcc = cl < rL2 - a * breakATR and close1 < rL2 - a * breakATR
            upSus = loCDep > rH2 + dBuf
            dnSus = hiCDep < rL2 - dBuf
            upGo = (upAcc and (sosScore >= strengthMinScore or mbSOS)) or upSus
            dnGo = (dnAcc and (sowScore >= strengthMinScore or mbSOW)) or dnSus
            provLimit = phase_idle_limit(PHASE_C, True, p2)
            if upGo and not dnGo:
                upProv = s.provEdge == DIR_ACCUM and (not na(s.provBar)) and i - s.provBar <= provLimit
                if ageOKBull and upProv and mature2:
                    self._adopt_prov(s)
                    self._promote_d(s, DIR_ACCUM, sosScore, hi)
                    sig |= BIT_SPRING | BIT_SOS
                elif upSus and not upProv:
                    resetLate = RS_DEPART
            elif dnGo and not upGo:
                dnProv = s.provEdge == DIR_DIST and (not na(s.provBar)) and i - s.provBar <= provLimit
                if ageOKBear and dnProv and mature2:
                    self._adopt_prov(s)
                    self._promote_d(s, DIR_DIST, sowScore, lo)
                    sig |= BIT_UTAD | BIT_SOW
                elif dnSus and not dnProv:
                    resetLate = RS_DEPART
        if resetLate >= 0:
            self.rs[resetLate] += 1
            self.lastResetWhy = resetLate
            s = self.s = WS()

        # SOS/SOW confirmado tras LPS
        if s.phase == PHASE_D and s.outcome == DIR_ACCUM and s.ev == EV_LPS and not na(s.rangeHigh):
            if cl > s.rangeHigh + a * breakATR and relE >= strengthVolMult and cPos >= sosCloseMin:
                s.strBar = i; s.strTime = t; s.strPrice = hi; s.strScore = sosScore
                self._set_event(s, EV_SOS); sig |= BIT_SOS
        if s.phase == PHASE_D and s.outcome == DIR_DIST and s.ev == EV_LPSY and not na(s.rangeLow):
            if cl < s.rangeLow - a * breakATR and relE >= strengthVolMult and cPos <= sowCloseMax:
                s.strBar = i; s.strTime = t; s.strPrice = lo; s.strScore = sowScore
                self._set_event(s, EV_SOW); sig |= BIT_SOW

        # Fase E
        if s.phase == PHASE_D and (not na(s.rangeHigh)) and (not na(s.rangeLow)):
            eConf = self._conf(s)
            dAge = i - s.dStartBar if not na(s.dStartBar) else 0
            dMin = phaseD_min_bars(int(nz(s.pivLen, liveLen)))
            if s.outcome == DIR_ACCUM:
                s.outCount = s.outCount + 1 if cl > s.rangeHigh else 0
                eOppOKU = self.regime != REGIME_MARKDOWN or s.cfLPS
                eStdU = s.cfLPS and (not na(s.lpsBar)) and i - s.lpsBar >= confirmBars and dAge >= dMin \
                    and loCConf > s.rangeHigh and eConf >= minConfidencePhaseD
                eDirU = (not s.cfLPS) and dAge >= max(dMin, directAcceptanceBars) and loCDir > s.rangeHigh \
                    and eConf >= directAcceptanceConfidence
                if (eStdU or eDirU) and eOppOKU:
                    s.cfAccept = True; s.phase = PHASE_E; s.eStartBar = i; s.eStartTime = t
                    self.regime = REGIME_MARKUP; self.regimeBar = i
                    self._set_event(s, EV_MARKUP); sig |= BIT_E
            elif s.outcome == DIR_DIST:
                s.outCount = s.outCount + 1 if cl < s.rangeLow else 0
                eOppOKD = self.regime != REGIME_MARKUP or s.cfLPS
                eStdD = s.cfLPS and (not na(s.lpsBar)) and i - s.lpsBar >= confirmBars and dAge >= dMin \
                    and hiCConf < s.rangeLow and eConf >= minConfidencePhaseD
                eDirD = (not s.cfLPS) and dAge >= max(dMin, directAcceptanceBars) and hiCDir < s.rangeLow \
                    and eConf >= directAcceptanceConfidence
                if (eStdD or eDirD) and eOppOKD:
                    s.cfAccept = True; s.phase = PHASE_E; s.eStartBar = i; s.eStartTime = t
                    self.regime = REGIME_MARKDOWN; self.regimeBar = i
                    self._set_event(s, EV_MARKDOWN); sig |= BIT_E

        # ===== entrada =====
        entry_now = False
        if na(s.entryTime) and s.outcome != DIR_NONE:
            st = self.strict
            eMinConf = ENTRY_CONF[st]
            eMinTests = ENTRY_TESTS[st]
            eValFloor = phaseDValidationMin if st == "conservative" else max(45, phaseDValidationMin - 10)
            eVal = self._validation(s, int(nz(s.pivLen, liveLen)), trendScore, a)
            eReady = self._entry_readiness(s, eMinConf, eValFloor, a)
            eQuality = self._conf(s) >= eMinConf and eVal >= eValFloor and eReady >= eMinTests
            testBit = bool(sig & BIT_TEST) or bool(sig & BIT_CTEST)
            strengthBit = bool(sig & BIT_SOS) or bool(sig & BIT_SOW)
            lpsBit = bool(sig & BIT_LPS) or bool(sig & BIT_LPSY)
            aggTest = st == "aggressive" and testBit and eQuality
            aggStr = st == "aggressive" and strengthBit and eQuality and na(s.testTime)
            stdTest = st == "standard" and testBit and eQuality and s.testScore >= testMinScore
            stdLps = st == "standard" and lpsBit and eQuality
            consLps = st == "conservative" and lpsBit and eQuality
            if aggTest or aggStr or stdTest or stdLps or consLps:
                s.entryTime = t; s.entryPrice = cl
                s.entryKind = ENTRY_LPS if (stdLps or consLps) else (ENTRY_STRENGTH if aggStr else ENTRY_TEST)
                entry_now = True

        return {"i": i, "t": t, "sig": sig, "entry_now": entry_now, "close": cl, "atr": a,
                "phase": s.phase, "outcome": s.outcome, "stopSide": s.stopSide, "ev": s.ev,
                "type": self.type_of(s), "rangeHigh": s.rangeHigh, "rangeLow": s.rangeLow,
                "conf": self._conf(s) if s.stopSide != DIR_NONE else 0,
                "val": self._validation(s, int(nz(s.pivLen, liveLen)), trendScore, a),
                "exc": s.exc, "excTested": s.excTested, "excPrice": s.excPrice, "testPrice": s.testPrice,
                "entryKind": s.entryKind, "entryPrice": s.entryPrice, "entryTime": s.entryTime,
                "clPrice": s.climaxPrice, "reset": self.lastResetWhy}

    def next_step(self):
        s = self.s
        if s.phase == PHASE_NONE:
            return "Buscando SC / BC"
        side = "SC" if s.stopSide == DIR_ACCUM else "BC"
        if s.phase == PHASE_A:
            return f"Confirmando {side} y esperando AR + ST" if s.absorbed else f"Confirmando absorción tras el {side}"
        if s.phase == PHASE_B:
            return "Construyendo causa: vigilar Spring/UTAD o test terminal"
        if s.phase == PHASE_C:
            want = "SOS" if s.outcome == DIR_ACCUM else "SOW"
            return f"Esperando {want}" if (not s.exc or s.excTested) else f"Esperando test del {'Spring' if s.outcome == DIR_ACCUM else 'UTAD'}"
        if s.phase == PHASE_D:
            return "Esperando " + ("LPS" if s.outcome == DIR_ACCUM else "LPSY") if na(s.lpsTime) else "Esperando aceptación fuera del rango"
        return "Tendencia en marcha (gestión, no entrada)"
