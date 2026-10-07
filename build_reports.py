# Reading guide: LEGACY report generator tied to the initial precision protocol.
# Imports load results/precision.csv, config/validation/resources and construct
# static page descriptions. This is not an import-safe general reporting library.
# The strict protocol check prevents a different experiment being silently shown
# with old narrative text. Current common-noise results need their own presentation.
# figures -> build_pdf -> build_html is the intended CLI execution order.
# The PDF preserves an existing historical foundation and appends generated pages;
# the HTML template embeds the same saved evidence and figures for offline use.
# Rendering creates/overwrites files under reports; no sorting is performed.
# Comments added here explain the generator without revising dated report claims.

"""Rebuild both reports from saved evidence; never invent or rerun result rows.

The historical-foundation PDF preserves the already-agreed definitions and
five-architecture derivations. New experimental chapters replace the old
precision sweep throughout. All new tables/figures use results/precision.csv.
"""
from pathlib import Path
import base64, csv, html, io, json, math, re, os, tempfile
os.environ.setdefault('MPLCONFIGDIR', tempfile.mkdtemp(prefix='apc_matplotlib_'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import fitz
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, Preformatted
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT=Path(__file__).resolve().parent
R=ROOT/'results';OUT=ROOT/'reports';ASSET=ROOT/'report_assets'
OUT.mkdir(exist_ok=True)
# Import-time evidence loading: these CSV rows belong to the dated initial
# protocol. Do not point this generator at common-noise/quality tables without
# also revising its schema checks and authored narrative.
ROWS=list(csv.DictReader((R/'precision.csv').open()))
for row in ROWS:
    for key in ['key_bits','input_bits','output_bits','n','trials','correct_sorts','stable_sorts','valid_outputs','comparisons','false_ties','sign_reversals','saturations']:
        row[key]=int(row[key])
    for key in ['success_fraction','ci_low','ci_high','stable_success','valid_output_fraction','noise_output_lsb']:
        row[key]=float(row[key])
CONFIG=json.loads((R/'config.json').read_text())
expected_cases=[dict(key_bits=b,input_bits=b,output_bits=b,sizes=[2**i for i in range(1,b+1)]) for b in [4,8]]
if (CONFIG['precision_cases']!=expected_cases or CONFIG['trials']!=1000 or
    CONFIG['noise_output_lsb']!=0.25 or CONFIG['families']!=['distinct','duplicates_allowed'] or
    CONFIG['modes']!=['ideal','quantized','quantized_noise']):
    raise ValueError('This report template documents the agreed initial 4/8-bit protocol only. Adapt its text before reporting a different protocol.')
VALIDATION=json.loads((R/'validation.json').read_text())
RES=list(csv.DictReader((R/'resources.csv').open()))


# Select the saved row identified by key width, N, family, mode and architecture.
# Return the first exact match from the already parsed global ROWS collection.
# Missing evidence raises StopIteration rather than inventing an interpolated value;
# the historical input protocol is checked when this script is imported.
def lookup(b,n,family,mode,arch):
    return next(r for r in ROWS if (r['key_bits'],r['n'],r['family'],r['mode'],r['architecture'])==(b,n,family,mode,arch))


# Build 4-bit and 8-bit static plots from saved success fractions/intervals.
# Each contains distinct-key and duplicates-allowed panels, with paired bitonic
# curves represented once and rank curves shown separately.
# Write PNG and SVG versions under reports; their filenames feed both renderers.
# The shaded intervals come from CSV evidence, not a new fit or resimulation.
def figures():
    """Publication-style static figures, with every point from the saved CSV."""
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    for b in [4,8]:
        fig,axes=plt.subplots(1,2,figsize=(10,3.7),sharey=True,layout='constrained')
        for ax,fam in zip(axes,['distinct','duplicates_allowed']):
            for arch,col in [('Beyette','#1964a0'),('Louri','#128168')]:
                for mode,ls,mk in [('quantized','--','s'),('quantized_noise','-','o')]:
                    rr=[r for r in ROWS if r['key_bits']==b and r['family']==fam and r['mode']==mode and r['architecture']==arch]
                    n=[r['n'] for r in rr];y=np.array([r['success_fraction'] for r in rr])*100
                    name=('Bitonic (both)' if arch=='Beyette' else 'Rank')+(' + noise' if mode.endswith('noise') else ', no noise')
                    ax.plot(n,y,linestyle=ls,marker=mk,color=col,label=name,markersize=4)
                    if mode.endswith('noise'):
                        lo=np.array([r['ci_low'] for r in rr])*100;hi=np.array([r['ci_high'] for r in rr])*100
                        ax.fill_between(n,lo,hi,color=col,alpha=.12)
            ax.set_xscale('log',base=2);ax.set_xticks(n,labels=n);ax.set_ylim(-2,102)
            ax.set_title('Distinct keys' if fam=='distinct' else 'Duplicates allowed')
            ax.set_xlabel('Array length N');ax.grid(alpha=.18)
        axes[0].set_ylabel('Correct complete sorts (%)')
        handles,labels=axes[0].get_legend_handles_labels()
        fig.legend(handles,labels,loc='outside lower center',ncol=2,frameon=False,fontsize=9)
        fig.suptitle(f'{b}-bit keys, {b}-bit input, {b}-bit signed output; 1,000 trials per point')
        fig.savefig(OUT/f'precision_{b}bit.png',dpi=180)
        fig.savefig(OUT/f'precision_{b}bit.svg')
        plt.close(fig)


PAGES=[]
# Append one declarative page to the global PAGES list; return None.
# title is a heading string and blocks are tagged tuples from the helpers below.
# Building this list describes content only; layout occurs later in build_pdf/html.
def page(title,*blocks):PAGES.append({'title':title,'blocks':list(blocks)})
# Return a ('p', value) content tuple representing a body paragraph.
# This helper does not render or write files. PDF/HTML dispatchers interpret the
# same tag later, keeping content selection separate from output formatting.
def p(s):return ('p',s)
# Return a ('h', value) content tuple representing a subheading.
# This helper does not render or write files. PDF/HTML dispatchers interpret the
# same tag later, keeping content selection separate from output formatting.
def h(s):return ('h',s)
# Return a ('eq', value) content tuple representing a equation-style callout.
# This helper does not render or write files. PDF/HTML dispatchers interpret the
# same tag later, keeping content selection separate from output formatting.
def eq(s):return ('eq',s)
# Return ('table', headers, rows, widths) as a declarative content block.
# Optional widths are PDF column widths in points; None requests equal widths.
# The HTML renderer uses the same cell content with its responsive table wrapper.
def table(headers,rows,widths=None):return ('table',headers,rows,widths)
# Return a ('code', value) content tuple representing a literal code sample.
# This helper does not render or write files. PDF/HTML dispatchers interpret the
# same tag later, keeping content selection separate from output formatting.
def code(s):return ('code',s)
# Return a ('picture', value) content tuple representing a saved figure filename.
# This helper does not render or write files. PDF/HTML dispatchers interpret the
# same tag later, keeping content selection separate from output formatting.
def picture(name):return ('picture',name)
# Return a ('diagram', value) content tuple representing a mapping selector, bitonic or rank.
# This helper does not render or write files. PDF/HTML dispatchers interpret the
# same tag later, keeping content selection separate from output formatting.
def diagram(kind):return ('diagram',kind)


# The following page declarations are historical authored report content.
# They are not fresh scientific conclusions recalculated from current branches.
# The rendering helpers below consume their tagged blocks for PDF and HTML.
page('7.2 Precision and nonlinearity: updated evidence',
 p('The public Q.ANT evidence in the preceding pages is retained as a dated snapshot checked on 1 October 2026. This revision reruns the numerical experiment on 2 October 2026. It does not establish a new device specification or execute the Q.ANT SDK.'),
 table(['Quantity','Meaning in this study'],[
 ['key_bits = 4 or 8','Declared integer domain: 0..15 or 0..255. It determines input values and the maximum tested N.'],
 ['input_bits = 4 or 8','Number of bits in the hypothetical unsigned input quantizer. Stored independently of key_bits.'],
 ['output_bits = 4 or 8','Number of bits in the hypothetical signed difference-output quantizer. Stored independently of input_bits.'],
 ['BF16','Software storage format at the inspected SDK boundary. It is not emulated by these fixed-point quantizers.'],
 ['ENOB','Effective precision from a specified measurement. Neither 4 nor 8 is asserted to be Q.ANT ENOB.'],
 ['Gaussian sigma = 0.25 output steps','An agreed illustrative sensitivity setting; not a measured or paper-derived Q.ANT noise amplitude.']]),
 h('What the software evidence actually supports'),
 p('At pinned SDK commit 72a2d99f10240b6df3c6d0f636dfa0e2b5d38902, linear_fprop defines Y=XW^T and calls a batched MVM driver. The nonlinear interface describes tcos(u)*v. In the inspected implementation, relu_fprop applies a software maximum rather than demonstrating native optical ReLU. [10]'),
 p('Supported physical matrix dimensions, small-difference accuracy, data-transfer costs and unregenerated cascade depth remain open questions. Eight channels do not establish an 8 by 8 matrix. Vendor GOPS do not establish sorts per second. The experiment therefore evaluates a proposed mathematical mapping with explicit numerical assumptions.'))

page('8. One difference operation, two sorting mappings',
 p('Both mappings need to decide which of two records comes first. Their common candidate arithmetic is a signed subtraction. For B independent pairs, gather a B by 2 input matrix and use one output weight row [1, -1].'),
 eq('X = [[a1,b1], ..., [aB,bB]], W = [1,-1], Y = X W^T.'),
 p('The multiplication produces differences, not sorted records. A sign decision, tie rule and record movement still follow. The code computes this subtraction directly in NumPy; it does not pretend that a Python matrix expression invokes an optical device.'),
 diagram('bitonic'),
 p('<b>Bitonic:</b> pairs change between dependent layers. Each layer needs its measured signs before the next layer knows which original records occupy each position. The cycle repeats K times; source shuffle-only bypass steps do not add arithmetic noise.'),
 diagram('rank'),
 p('<b>Rank:</b> the unordered pairs can all be formed from the original input. Decisions increment electronic integer ranks. Records are placed only when the ranks form a permutation of 0..N-1. A finite device may tile the pair phase; one wide logical stage is not a one-call latency guarantee.'),
 p('The green arithmetic block in the diagrams is a proposed photonic operation. Every block is executed in software in this pilot. Encoding/readout and electronic control boundaries are explicit; no optical chaining is assumed.'))

page('8.1 Normalize keys without hiding their range',
 p('The user selected whole numbers including zero, with conventional ranges 0..15 and 0..255. A b-bit unsigned representation has 2^b levels and a maximum integer of 2^b-1. Invalid raw inputs are rejected before normalization.'),
 eq('M = 2^key_bits - 1; Lin = 2^input_bits.<br/>u(x) = x (1 - 1/Lin) / M.<br/>Qin(u) = rint(Lin*u) / Lin.'),
 p('The maximum allowed key maps exactly to the largest unsigned input level, 1-1/Lin. The scale is fixed by the declared domain, not the minimum and maximum in each test array. Every architecture receives the same scale.'),
 table(['Matched case','Normalization','Input step','Largest input level'],[
 ['4-bit key/input','u=x/16','1/16','15/16'],['8-bit key/input','u=x/256','1/256','255/256']]),
 p('For these matched cases, every integer key is represented exactly at the input: input quantization introduces no error. The experiment still records input_bits separately so future experiments can vary it independently. Input precision and output precision must not be conflated.'),
 h('Why use this scale?'),
 p('It uses the full representable input interval, preserves order because the scale is positive, and makes key spacing comparable across arrays in a case. It is a transparent experimental choice, not a universally optimal normalization proven by the supplied literature. Block floating point and data-dependent scaling are possible later alternatives, with additional scaling and execution costs.'),
 code('validate_keys(raw_keys, key_bits)\nscale = (1 - 1 / input_levels) / maximum_key\nq = np.rint(raw_keys * scale * input_levels) / input_levels'))

page('8.2 Quantize the signed difference',
 p('A subtraction may be negative. The retained output model therefore uses a signed grid, whereas the input grid is unsigned. With Lout output levels, the interval is [-1, 1-h] and h is one output quantization step.'),
 eq('Lout = 2^output_bits; h = 2/Lout.<br/>d = Qin(u(a)) - Qin(u(b)).<br/>epsilon ~ Normal(0, (eta*h)^2), eta = 0 or 0.25.<br/>d_measured = h * clip(rint((d+epsilon)/h), -Lout/2, Lout/2-1).'),
 table(['Operation','Reason / explicit convention'],[
 ['Divide by h','Express the noisy difference in output-code units.'],
 ['rint','Choose the nearest integer code; exact half steps go to the even integer.'],
 ['clip','Model output saturation if the rounded code is outside the signed converter range.'],
 ['Multiply by h','Return the represented difference in normalized units.']]),
 p('Raw-key rejection and output saturation are different rules. A key 16 is rejected in the 4-bit domain. A valid measured subtraction can saturate at an output endpoint because of the signed grid or noise; this is counted as a numerical event, not silently treated as an input error.'),
 p('The output grid, nearest-even rounding and exact digital operations are modeling conventions retained from the earlier pilot. They are not claimed to reproduce a Q.ANT ADC transfer function. Gaussian errors are independent across comparison events and trials; correlated, signal-dependent and stage-accumulating optical errors are outside this experiment.'),
 code('codes = np.rint(noisy / output_step)\nresult = np.clip(codes, -levels // 2, levels // 2 - 1)\nreturn result * output_step'))

page('8.3 Follow one comparison: keys 10 and 9',
 p('Use 8-bit keys, input quantization and output quantization. Both inputs are valid. The table first calculates quantization alone, then illustrates one possible noise sample. The sample is chosen to explain the arithmetic; it is not a fixed noise value used in the Monte Carlo run.'),
 table(['Step','No added noise','Example epsilon = +1/512'],[
 ['Raw keys','10, 9','10, 9'],['Normalize and quantize inputs','10/256, 9/256','10/256, 9/256'],
 ['Difference d','1/256','1/256'],['Output step h','1/128','1/128'],
 ['Add epsilon','1/256','3/512'],['Divide by h','0.5','0.75'],
 ['Round to nearest even','0','1'],['Clip code to [-128,127]','0','1'],
 ['Return code times h','0','1/128'],['Decision for [10,9]','Tie: earlier index first','10 is greater than 9'],
 ['Two-record ascending output','[10,9], incorrect','[9,10], correct']]),
 p('Here sigma=0.25h=1/512. Each simulated comparison draws its own sample, including negative samples. A sample -1/512 would leave a zero measured difference. The final value is a quantized comparison signal; original key values 10 and 9 remain unchanged.'),
 h('The same issue at 4 bits'),
 p('Inputs 10/16 and 9/16 differ by 1/16, but the output step is 1/8. The output code is again rint(0.5)=0 without noise. Matching input and output bit counts does not give matching input and signed-output resolution.'))

page('8.4 Bitonic: from source routing to code',
 p('Bitonic networks build short ascending and descending runs, then merge them through a fixed sequence of compare-exchanges. For N=2^m, the compact schedule has K=m(m+1)/2 active layers, each with N/2 pair comparisons. Beyette and Desmulliez implement a fixed perfect-shuffle schedule with P=m^2-m+1 processing steps, including bypasses. [5,6]'),
 table(['Source mechanism','Python representation','Reason'],[
 ['Optical perfect-shuffle wiring','Move values and original indexes to fixed destination indexes.','Presents the correct logical pairs to adjacent nodes.'],
 ['Node difference / ordering decision','Difference(raw_a,raw_b); inspect sign and original indexes.','Proposed hybrid replacement for source comparison logic.'],
 ['Ascending/descending node control','A stored schedule flag selects the exchange direction.','Creates and merges bitonic subsequences.'],
 ['Electronic storage / recirculation','Update the current original records after each step.','Reuses the same logical node positions.'],
 ['Bypass step','Permutation only; no Difference call.','Does not invent extra numerical comparisons.']]),
 eq('For i &lt; N-1: destination(i) = 2i mod (N-1).<br/>The last wire remains at N-1.'),
 p('For N=8, destination=[0,2,4,6,1,3,5,7]. This is a wiring permutation, not a rank vector. The source example [4,8,1,3,2,7,5,6] becomes [4,8,3,1,2,7,6,5] after its first comparison step and [1,2,3,4,5,6,7,8] after seven processing steps, six of them active.'),
 p('Both named architectures run this schedule with identical numerical assumptions and matched error samples. Equal precision results are expected. Their physical node design, storage and historical timing remain distinct.'))

page('8.5 Bitonic: the exchange decision',
 code('d = difference(a, b)  # RAW keys; model normalizes internally\ngreater = (d > 0) | ((d == 0) & (index_a > index_b))\nexchange = np.where(ascending, greater, ~greater)\nleft  = np.where(exchange, b, a)\nright = np.where(exchange, a, b)'),
 p('A positive measured difference places a after b in an ascending comparison. If the measured difference is zero, the original input index breaks the tie. For a descending node the order is reversed. Keys and their indexes are always exchanged together.'),
 table(['Compact reference layer','Example state for [7,2,5,1]'],[
 ['Input','[7,2,5,1]'],['1: adjacent pairs, opposite directions','[2,7,5,1]'],
 ['2: distance-two pairs, ascending','[2,1,5,7]'],['3: adjacent pairs, ascending','[1,2,5,7]']]),
 p('This compact N=4 example explains the comparison layers; the evaluated fixed-shuffle implementation also carries out its explicit routing. Both representations agree ideally. Comparisons can be wrong while exchanges still preserve every record exactly once: the bitonic validity fraction is therefore always 100% in this model, even when the correct-sort fraction is low.'),
 h('What is adapted'),
 p('Historical optical interconnects and source node logic are not emulated at component level. The modern proposal retains a known sorting schedule but replaces its ordering information with a finite-precision pair-difference signal. This is why the experiment cannot be described as a hardware reproduction of either historical device.'))

page('8.6 Rank sorting: source matrix and modern adaptation',
 p('Louri broadcasts the input into a two-dimensional comparison structure. A difference matrix and a triangular bias resolve order and ties. Thresholded entries are summed by column to obtain one-based ranks, followed by output placement. The source includes smart-pixel electronic functions; it is not a purely linear optical MVM. [7]'),
 eq('For the reproduced source convention:<br/>Delta_ij = x_j - x_i.<br/>bias_ij = 1 if i &gt; j, otherwise 0.<br/>R_ij = 1 if Delta_ij - bias_ij &gt;= 0, otherwise 0.<br/>rank_j = sum_i R_ij.'),
 table(['Source example','Result'],[
 ['Input','[7, 8a, 2, 8b, 5]'],['One-based ranks','[3,4,1,5,2]'],
 ['Zero-based ranks','[2,3,0,4,1]'],['Stable output','[2,5,7,8a,8b]']]),
 p('The code validates this original matrix example separately. The numerical sweep then uses a deliberate adaptation: compare each unordered pair once, infer the complementary decision, sum integer ranks electronically and scatter original records electronically. There are N(N-1)/2 measured differences rather than N^2 independently evaluated matrix entries.'),
 p('The source triangular unit bias is valid for its integer-key formulation. It is not blindly added as a unit offset to normalized analog values. The adaptation instead resolves a measured zero by original index. Ideal equivalence does not imply that its noisy physical behavior is identical to the paper.'))

page('8.7 Rank: count, validate, place',
 table(['Unordered pair from [7,2,5,1]','Record receiving one rank increment'],[
 ['7 versus 2','7'],['7 versus 5','7'],['7 versus 1','7'],
 ['2 versus 5','5'],['2 versus 1','2'],['5 versus 1','5']]),
 eq('Final zero-based ranks: [3,1,2,0].<br/>Place input record i at output position rank_i.<br/>Output: [1,2,5,7].'),
 code('left, right = np.triu_indices(n, 1)\nd = difference(keys[:, left], keys[:, right])\nleft_is_larger = d > 0\n# Every pair increments the rank of exactly one record.\n# A measured tie favors the earlier original index.\nvalid = np.all(np.sort(ranks, axis=1) == np.arange(n), axis=1)'),
 p('Original indices satisfy left&lt;right, so d=0 assigns the increment to the later record. A rank counts how many records are judged to come before that record. The electronic sums use exact integers.'),
 h('Why a rank output can fail structurally'),
 p('Inconsistent comparisons can report a&gt;b, b&gt;c and c&gt;a. Then all three ranks can be 1. Three records request the same position, so there is no valid output permutation. Such a trial fails and is not repaired by a digital sort.'),
 p('Distinct ranks can still describe an incorrect ordering. Consequently the experiment reports validity, correct sorting and stable sorting separately. Correctness is always divided by all 1,000 trials, including invalid ones.'))

page('9. What was validated against the papers',
 table(['Source / locator','Reproduced','Adapted or unverified'],[
 ['Beyette [5], Eq.1; section 3.C','P=m^2-m+1. N=8, w=3 gives P=7 and P+w-1=9 cycles.','Comparison arithmetic replaced by shared Difference model. Physical timing, losses and hardware operation not measured.'],
 ['Desmulliez [6], Fig.3; Eq.8','Eight-key trace; seven steps/six active layers. 1024 keys, w=8, F=100MHz: 9.1 us; about 900.22 Mbit/s.','Projected complete-system design point, not a measured 100MHz sorter. Identical numerical schedule to Beyette here.'],
 ['Louri [7], Eqs.3-7; timing discussion','Original matrix ranks [3,4,1,5,2]. Reported component arithmetic: 60.2 ns full cycle, 36.8 ns period.','Sweep uses unordered pairs and electronic sums/placement. Detector estimate discrepancy remains unresolved.']]),
 p('Louri lists a detector estimate of about 13.33 ns; using the stated 10 pJ and 1.5 mW gives E/P about 6.67 ns. This factor-of-two issue is retained explicitly. Reproducing the timing sum does not resolve it or validate a measured complete sorter.'),
 p('The validation file records these source calculations separately from the new precision rows. No historical optical transit time is copied into a Q.ANT latency prediction. Source PDF hashes identify the supplied versions used in the research.'),
 h('What counts as evidence'),
 p('A published equation reproduced by arithmetic establishes transcription and interpretation of that equation. A worked example establishes the corresponding functional behavior. Ideal checks establish correctness on the tested inputs. None alone establishes the physical speed, energy or accuracy of a modern mapping.'))

page('9.1 Independent checks before and during the sweep',
 table(['Check','Actual test','Outcome'],[
 ['Source examples','Beyette equation; Desmulliez trace/operating point; Louri full matrix.','Pass; unresolved Louri physical discrepancy preserved.'],
 ['Small-network wiring','Every binary input at N=2,4,8, for all three cases.','Correct and stable.'],
 ['Every requested length','Random duplicates, endpoints, ascending, descending and all-equal arrays.','Ideal correct and stable.'],
 ['ReLU identity','All 256 ordered pairs from 0..15.','Exact min/max identity passes; not an optical test.'],
 ['Quantizer boundary control','All ordered pairs from each integer domain.','Input values exact; adjacent differences round to zero without noise.'],
 ['Invalid inputs','Negative, too large, fractional, nonfinite, boolean and text keys.','Rejected with position and permitted range.'],
 ['Noise reproducibility','Same trial streams executed together and in separate batches.','Identical outputs.'],
 ['Entire ideal sweep','72 configurations, 72,000 architecture runs.','100% correct and stable.'],
 ['Paired bitonic comparison','Every output, original index and validity mask.','Beyette and Desmulliez identical by design.']]),
 p('The two bitonic cases do not provide two independent sets of statistical evidence. Their paired outputs are checked, but confidence intervals are computed for each 1,000-trial configuration without pooling them.'),
 p('Checks are finite. The mathematical sorting-network construction supports general ideal behavior; the numerical run only supports the declared distributions, grid conventions and noise settings.'))

page('10. The agreed experimental protocol',
 table(['Parameter','Exact setting'],[
 ['Key domains','4 bits: all integers 0..15. 8 bits: all integers 0..255.'],
 ['Input/output bit settings','(4,4) or (8,8), stored as input_bits and output_bits separately.'],
 ['N, 4-bit case','2, 4, 8, 16'],['N, 8-bit case','2, 4, 8, 16, 32, 64, 128, 256'],
 ['Distinct family','Uniform sample without replacement, randomized order. At maximum N this is a permutation of the whole domain.'],
 ['Duplicates-allowed family','Independent uniform integer draws with replacement. An individual array need not actually contain duplicates.'],
 ['Trials and inputs','1,000 arrays per (key_bits,N,family); exact same arrays used by all modes and architectures.'],
 ['Conditions','Ideal; quantization only; quantization plus independent Gaussian noise, sigma=0.25 output steps.'],
 ['Master seed','20260930. Full seed contexts and input hashes saved.'],
 ['Digital operations','Exact comparisons of measured outputs, original-record movement, rank sums and placement.'],
 ['Rank failures','Count as failed sorts; no digital correction.']]),
 p('There are 12 size/bit cases, two input families, three conditions and three named architectures: 12*2*3*3=216 configurations. Each has 1,000 runs: 216,000 architecture executions on 24,000 generated input arrays.'),
 p('The comparison is between matched-width operating scenarios. As b increases, the domain expands as well as converter resolution. It does not isolate the causal effect of converter precision at a fixed key range.'))

page('10.1 Metrics and statistical interpretation',
 table(['Metric','Definition and denominator'],[
 ['Correct-sort fraction','Valid output equals the exact ascending sorted input; count / all 1,000 trials.'],
 ['Stable-sort fraction','Valid output record indexes equal a stable digital argsort; count / all trials.'],
 ['Validity fraction','Output positions form a permutation. Bitonic always preserves records; rank can have collisions.'],
 ['False-tie count','Number of comparison events with unequal raw keys but measured difference zero.'],
 ['Sign-reversal count','Measured difference has a strict sign opposite to the true nonzero difference.'],
 ['Output saturation count','Rounded output code exceeds a converter endpoint and is clipped.'],
 ['95% Wilson interval','Binomial sampling uncertainty for correct-sort fraction within this exact experiment.']]),
 p('A comparison-event count is not a count of failed arrays: an array may contain many such events. Saturation need not change a sign. A false tie can be resolved correctly or incorrectly depending on the original record indexes. These diagnostics explain mechanisms; the complete-sort metric answers the task requirement.'),
 p('NumPy sort provides ground truth only; it is not used to repair outputs and is not timed as a competitive CPU/GPU baseline. Kendall tau is not reported in this run: invalid rank outputs require an explicit treatment before an ordering-distance metric would be comparable.'),
 p('For 0 correct outputs in 1,000 trials, the Wilson upper bound is about 0.383%. For 1,000 correct outputs it gives a lower bound about 99.617%. Neither observation proves a population probability exactly zero or one.'),
 p('Confidence intervals do not capture unmodeled device effects or uncertainty in the numerical model. Small observed differences between algorithms do not establish superiority. A paired statistical comparison would use the saved per-trial outcomes and a declared hypothesis.'))

page('11. Results: what the new run establishes',
 p('<b>Ideal correctness:</b> every tested ideal case succeeds, including duplicates and the maximum lengths. The proposed functional mappings work when comparison information is exact.'),
 p('<b>Limited precision:</b> adjacent keys can become false ties even without noise. Correct complete sorts become rare as N becomes large relative to the key domain. The raw integer range is now explicit and no accepted input is silently clipped.'),
 p('<b>Architecture distinction:</b> the two bitonic cases give exactly the same results under the shared comparison model. Rank can additionally produce invalid output positions. The experiment identifies no universal winner.'),
 picture('precision_4bit.png'),
 p('Dashed: quantization only. Solid: quantization plus sigma=0.25 output steps. Shading: 95% Wilson intervals for noisy points. Ideal cases are 100% throughout and omitted from the plot for readability. Both bitonic curves overlap by construction.'),
 p('The exact tables on the next pages report correct runs out of 1,000. Complete three-architecture rows, intervals, stable counts and validity counts are available in the HTML inspector and precision.csv.'))

# Select saved counts for one key width and input family over configured sizes.
# Show quantized and noisy bitonic/rank correct counts plus noisy rank validity.
# Return a table block with explicit PDF widths; this aggregates existing rows
# without rerunning sorters, calculating new metrics, or altering their denominators.
def result_table(b,family):
    rr=[]
    for n in next(c['sizes'] for c in CONFIG['precision_cases'] if c['key_bits']==b):
        a=lookup(b,n,family,'quantized','Beyette');l=lookup(b,n,family,'quantized','Louri')
        an=lookup(b,n,family,'quantized_noise','Beyette');ln=lookup(b,n,family,'quantized_noise','Louri')
        rr.append([str(n),str(a['correct_sorts']),str(l['correct_sorts']),str(an['correct_sorts']),str(ln['correct_sorts']),str(ln['valid_outputs'])])
    return table(['N','Bitonic: no noise','Rank: no noise','Bitonic: noise','Rank: noise','Rank valid: noise'],rr,[30,83,83,83,83,103])

for b in [4,8]:
    for family in ['distinct','duplicates_allowed']:
        page(f'11.{1+(b==8)*2+(family=="duplicates_allowed")} {b}-bit results: '+('distinct keys' if family=='distinct' else 'duplicates allowed'),
             p(f'Raw keys 0..{2**b-1}; input_bits={b}; output_bits={b}. Every entry below is a count out of 1,000 trials. Bitonic denotes each of Beyette and Desmulliez; counts are not pooled.'),
             result_table(b,family),
             p('Ideal arithmetic: 1,000/1,000 correct and stable for every N and every architecture in this table. Noise refers to independent Gaussian sigma=0.25 output steps.'),
             p('Rank validity is shown separately from correctness. A valid permutation may still be incorrectly ordered. Invalid ranks remain in the denominator of the correct-sort fraction.'),
             picture('precision_8bit.png') if b==8 and family=='distinct' else
             p('For duplicate keys, complete key order and stable record order are different requirements. The saved stable_sorts field tests the original record identities, not just the key values.'),
             p('These data are sensitivity results for the declared numerical mapping. They are not measured Q.ANT sorting probabilities.'))

page('11.5 Read the results without overclaiming',
 table(['Representative noisy case','Bitonic: correct / valid','Rank: correct / valid'],[
 [f'{b} bits, N={n}, '+('distinct' if fam=='distinct' else 'duplicates allowed'),
  f"{lookup(b,n,fam,'quantized_noise','Beyette')['correct_sorts']}/1000; 1000/1000",
  f"{lookup(b,n,fam,'quantized_noise','Louri')['correct_sorts']}/1000; {lookup(b,n,fam,'quantized_noise','Louri')['valid_outputs']}/1000"]
 for b,n,fam in [(4,16,'distinct'),(8,16,'distinct'),(8,32,'distinct'),(8,64,'distinct'),(8,256,'duplicates_allowed')]]),
 h('Why noise sometimes raises the success fraction'),
 p('An adjacent-key difference sits exactly at half an output step. With nearest-even rounding, it becomes zero deterministically without noise. A small positive or negative perturbation can move it into a nonzero code. This can resolve an otherwise misleading tie; the same noise can also create errors, including errors between truly equal keys.'),
 p('This is a quantizer-boundary effect of the chosen model and input lattice. It does not support adding noise to a real sorter or treating Gaussian noise as physically beneficial in general.'),
 h('An independent two-key control'),
 p('Without noise, exhaustive enumeration of every ordered distinct pair gives a success probability of 93.75% for 4 bits and 99.609375% for 8 bits. The reason is simple: there are L(L-1) ordered distinct pairs and L-1 descending adjacent pairs are misread as ties, giving failure probability 1/L. This independently explains the small-N Monte Carlo behavior.'),
 p('At maximum N, distinct arrays contain the entire domain, exposing every adjacent spacing. At a fixed small N, the 8-bit domain produces sparser random arrays than the 4-bit domain. Both density and numerical resolution must be considered when comparing their results.'),
 p('<b>In raw-key units:</b> multiplying by the normalization denominator gives an output step of 2 integer-key units and noise sigma=0.5 key units in both matched-width scenarios. Thus increasing both domain width and converter width does not improve adjacent-integer resolution in this model. A fixed-domain converter sweep is needed to isolate that effect.'))

page('11.6 Resource counts and timing boundaries',
 table(['N','Active K','Shuffle P','Bitonic differences','Rank differences'],[
 [str(n),str((n.bit_length()-1)*n.bit_length()//2),str((n.bit_length()-1)**2-(n.bit_length()-1)+1),
  str(n*(n.bit_length()-1)*n.bit_length()//4),str(n*(n-1)//2)] for n in [2,4,8,16,32,64,128,256]]),
 p('The counts are per input array. Bitonic uses N/2 differences in each of K dependent active layers. Rank uses N(N-1)/2 differences followed by electronic accumulation and placement. P counts the researched shuffle processing steps, including bypasses; it is not a count of noisy subtraction rounds.'),
 p('For N=256, the bitonic mapping evaluates 4,608 differences in 36 active layers and the rank mapping evaluates 32,640 pair differences. Rank exposes more independent work; whether that offsets its larger work and data movement depends on the device.'),
 h('What is not a measured timing result'),
 p('No Q.ANT latency or throughput is inferred from NumPy execution time. Source clocks, vendor GOPS and optical transit times have different boundaries. A modern timing model must establish batching, supported dimensions, dispatch, host/device transfers, output conversion, electronic decisions and memory costs.'),
 p('The simulator stores all pairs in a batch for convenience. Its Python memory use and vectorization are not measurements of required physical photonic area or an optimized hardware implementation. The earlier C table is structural accounting under its stated conventions.'))

page('12. Next experiments and hardware questions',
 table(['Priority','Question','Evidence needed'],[
 ['1. Numerical control','How much failure comes from signed output resolution?','Keep the key range and exact input arrays fixed; vary input_bits and output_bits independently, then compare the same metrics.'],
 ['2. Candidate kernel','Can the [1,-1] pair kernel run efficiently?','Accepted dimensions, ranges, batching/tiling, weight loading and measured sign-error behavior.'],
 ['3. Timing boundary','What dominates a complete sort?','Dispatch, transfer, encode/readout, device arithmetic and electronic control timings under one stated boundary.'],
 ['4. Optical nonlinearity','Can a useful comparator/min-max be implemented?','Documented transfer function, operating interval, precision and gain; do not substitute a function name for device evidence.'],
 ['5. Regeneration interval','How many nonlinear stages can be cascaded?','Calibrated noise/loss propagation and actual optical chaining support; otherwise explicitly hypothetical parameters.'],
 ['6. Energy','Does either mapping have a system advantage?','Measured or justified power/event energies with the same correctness and system boundaries as the digital baseline.']]),
 p('The first follow-up should separate key width from signed output resolution. Merely repeating more Monte Carlo trials cannot resolve a systematic quantizer limitation. The current run is useful evidence for choosing that experiment.'),
 p('A future bitonic cascade may use r=max(a-b,0), min=a-r and max=b+r. This is an exact mathematical identity. It requires a defensible nonlinear physical operation and signal path before a regeneration-interval model can claim hardware relevance.'),
 p('PRISM remains related work on photonic similarity scoring followed by electronic selection. Full sorting, stable sorting and top-k retrieval must have separate task definitions and baselines. [12]'))

page('13. Thesis registration: a concrete research goal',
 h('Proposed title'),
 p('<b>Hardware-Aware Evaluation of Bitonic and Rank Sorting on Hybrid Photonic Accelerators</b>'),
 h('Goal'),
 p('Establish under which documented or explicitly parameterized precision, resource and execution conditions a bitonic or rank-based mapping can perform correct full sorting on a hybrid photonic platform. Use Q.ANT as a reference where its public evidence supports the mapping. Do not assume an efficiency advantage.'),
 table(['Research question','Current evidence / next contribution'],[
 ['How does the proposed C model relate to earlier models?','Preserved historical comparison and five-architecture derivations.'],
 ['Do the proposed mappings sort ideally?','Selected paper examples, independent checks and every ideal sweep case pass.'],
 ['Where do they fail numerically?','False ties from output resolution, noise-related comparison errors, and inconsistent ranks.'],
 ['Which algorithm is preferable under specified conditions?','Compare at the same correctness requirement and documented resource/timing boundary. No universal winner established.'],
 ['How do nonlinearity and regeneration change the result?','Central next experiment, contingent on defensible optical functions and cascade assumptions.']]),
 p('The registration milestone is a reproducible functional comparison and a precise hardware evidence gap. An energy-efficiency verdict follows only after mapping, timing and power evidence are sufficient. A negative result can still identify useful limits and conditions for photonic sorting.'),
 p('Deliverables now available: documented code, complete configuration, saved inputs and outcomes, all result rows, source-validation records, operation counts, this updated PDF and an offline interactive HTML report.'))

page('14. Reproduce and inspect the evaluation',
 p('Extract qant_sorting_pilot.zip and open its qant_sorting_pilot folder in VS Code. Python 3.12 and the pinned dependencies reproduce the tested software environment. The included results can be read without rerunning.'),
 h('Windows PowerShell'),
 code('py -3.12 -m venv .venv\n.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt\n.\\.venv\\Scripts\\python.exe validate.py\n.\\.venv\\Scripts\\python.exe evaluate.py\n.\\.venv\\Scripts\\python.exe build_reports.py'),
 h('Linux / macOS'),
 code('python3 -m venv .venv\n.venv/bin/python -m pip install -r requirements.txt\n.venv/bin/python validate.py\n.venv/bin/python evaluate.py\n.venv/bin/python build_reports.py'),
 p('Choose the project .venv with VS Code: Python: Select Interpreter. The commands above use that environment explicitly, so shell activation is optional. Read README.md for the entry points and example input.'),
 p('evaluate.py overwrites its output folder. To retain the supplied results while experimenting, pass --output results_trial and a separate --config path. build_reports.py reads the canonical results folder. Only the accepted (4,4) and (8,8) settings are reported in this revision.'),
 p('The HTML report works offline and contains all 216 rows. Its selectors change the view only; they do not start simulations or fabricate predictions. The worked quantizer example is explicitly illustrative.'))

page('14.1 Configuration, seeds and the evidence files',
 table(['File','Meaning'],[
 ['config.json / results/config.json','Requested sweep and the saved run configuration.'],
 ['results/precision.csv','216 rows: exact counts, fractions, Wilson intervals, precision settings and seed contexts.'],
 ['results/inputs.npz','24 datasets of 1,000 arrays; identified by bit width, N and family.'],
 ['results/trial_outcomes.npz','One matrix per case: columns correct, stable, valid. Rows are trial indexes.'],
 ['results/failures.json','First incorrect trial per failing case, with input, expected output, actual output and record indexes.'],
 ['results/resources.csv','Per-array pair counts, active rounds and source shuffle steps.'],
 ['results/validation.json','Source examples, mathematical controls, input errors and full-sweep checks.'],
 ['results/run_metadata.json','Software versions, code hashes and runner wall time, explicitly not hardware latency.'],
 ['results/source_hashes.json','SHA-256 fingerprints of the supplied literature PDFs.']]),
 p('Input seeds use [master_seed,key_bits,N,family_id,0]. Noise seeds use [master_seed,key_bits,input_bits,output_bits,N,family_id,mode_id,stream_id,trial_index]. Families and modes follow config.json order. stream_id=1 for both bitonic cases and 2 for rank.'),
 p('Each trial has an independent NumPy generator. Consequently changing the memory batch size does not change the same trial sequence. The different algorithm schedules do not use identical per-pair noise samples: they use the same noise law, independent between rank and bitonic. The two bitonic cases intentionally share all samples.'),
 p('This run supersedes the previous N=8..64, spacing=1/4, 6..9-bit experiment as the current precision evidence. Old source examples and theory remain relevant; old result counts and input assumptions must not be combined with the new rows.'))

page('15. Glossary and evidence boundary',
 table(['Term','Meaning'],[
 ['Key / record','A sortable value / the value together with its original identity or payload.'],
 ['Stable sort','Equal true keys preserve their original order.'],
 ['False tie','Different raw keys produce a measured zero difference.'],
 ['Quantization step / LSB','Spacing between adjacent represented levels of the specified converter.'],
 ['Signed output','A difference representation admitting negative, zero and positive values.'],
 ['Normalization','Positive fixed scaling from the declared integer domain to an input signal range.'],
 ['Saturation','A rounded converter code outside the range is limited to an endpoint.'],
 ['Noise sigma','Standard deviation of the declared random error, here in output-step units.'],
 ['Rank collision','Multiple records request the same output position.'],
 ['Monte Carlo / seed','Repeated random trials / recorded initialization for reproducing them.'],
 ['Wilson interval','Sampling uncertainty for an observed success fraction; not device uncertainty.'],
 ['ENOB / BF16','Measured effective precision / a software floating-point storage format.'],
 ['Regeneration interval','Number of stages between signal restoration operations; not varied in this run.'],
 ['Optical depth D','Maximum unregenerated optical stages under the framework definition.'],
 ['Sensitivity / calibration','Vary declared assumptions / fit or verify against hardware measurements.']]),
 p('This pilot is a sensitivity study. Its assumptions and limitations are part of its result: it establishes a working functional baseline and exposes the precision questions that hardware evidence must address.'))

REFS=[
 ('[1] Thompson (1979). Area-Time Complexity for VLSI.','https://doi.org/10.1145/800135.804401'),
 ('[2] Caulfield (1991). Space-time complexity in optical computing.','https://doi.org/10.1007/BF01937172'),
 ('[3] Li and Monticone (2025). The spatial complexity of optical computing.','https://doi.org/10.1038/s41467-025-63453-8'),
 ('[4] Stirk and Athale (1988). Sorting with optical compare-and-exchange modules. Passive/restoring variants: p.1725.','https://doi.org/10.1364/AO.27.001721'),
 ('[5] Beyette et al. (1994). Bitonic sorting using an optoelectronic recirculating architecture. Eq.1, p.8165; section 3.C, p.8171.','https://doi.org/10.1364/AO.33.008164'),
 ('[6] Desmulliez et al. (1995). Perfect-shuffle interconnected bitonic sorter: optoelectronic design. Fig.3, p.5080; Eq.8 and projected design point, pp.5085-5088.','https://doi.org/10.1364/AO.34.005077'),
 ('[7] Louri et al. (1995). Constant-time parallel sorting algorithm and its optical implementation using smart pixels. Eqs.3-7; timing pp.3093-3094.','https://doi.org/10.1364/AO.34.003087'),
 ('[8] Mizutani et al. (2025; online 2024). In-network stable radix sorter using many FPGAs with high-bandwidth photonics.','https://doi.org/10.1364/JOCN.530695'),
 ('[9] Q.ANT photonic-computing product page. Vendor snapshot checked 1 October 2026; no new hardware measurement.','https://qant.com/photonic-computing/'),
 ('[10] Q.ANT Native Computing Toolkit. Inspected commit 72a2d99f10240b6df3c6d0f636dfa0e2b5d38902.','https://github.com/Q-ANT-GmbH/qant_native_computing_toolkit'),
 ('[11] LRZ. Photonic computers in real-world test. Separate operating context; conversion bits are not ENOB.','https://www.lrz.de/en/news/detail/photonic-computers-in-real-world-test'),
 ('[12] PRISM (2026). Photonic Similarity Engine for KV Cache Block Selection in Long-Context LLM Inference.','https://doi.org/10.48550/arXiv.2603.21576'),
 ('[13] The Physics of Optical Computing (2023).','https://doi.org/10.1038/s42254-023-00645-5'),
 ('[14] Noise in analog programmable-photonic computation (2026). Background for later physical noise modeling, not the source of sigma=0.25.','https://doi.org/10.48550/arXiv.2604.24541'),
 ('[15] Energy Efficiency in Analog Photonic Processors: Conversions and Losses at Scale (2026). System-boundary motivation.','https://doi.org/10.23919/ISC.2026.11520497')]
for start,end in [(0,8),(8,15)]:
    page('15.1 References' if start==0 else '15.2 Hardware and numerical background',
         *[p(f'{label}<br/><link href="{url}" color="#17658b">{url}</link>') for label,url in REFS[start:end]],
         p('Primary supplied literature and the preceding inspected hardware snapshot support the architectural account. Experimental settings and new results are explicitly identified as such. Source PDFs are not redistributed in the project ZIP or repository.'))


# Return a self-contained SVG illustrating the four steps of a mapping.
# kind='bitonic' selects dependent layer routing; the other branch depicts rank.
# Numbered boxes distinguish electronic work from a candidate photonic operation.
# The schematic is explanatory only: it does not establish measured device fusion,
# optical depth, latency, or absence of intermediate conversions.
def diagram_svg(kind):
    if kind=='bitonic':
        title='Bitonic: repeat K active layers'
        labels=[('ELECTRONIC','Gather current pairs'),('CANDIDATE PHOTONIC PATH','Encode > difference > read'),('ELECTRONIC','Sign and tie rule'),('ELECTRONIC','Exchange; next active layer')]
    else:
        title='Rank: all pairs, then ranks and placement'
        labels=[('ELECTRONIC','Gather original pairs'),('CANDIDATE PHOTONIC PATH','Encode > difference > read'),('ELECTRONIC','Sign and rank sums'),('ELECTRONIC','Validate; place records')]
    rects=[]
    for i,(group,label) in enumerate(labels):
        x=10+(i%2)*310;y=35+(i//2)*92
        fill=['#e9f0fc','#e1f3ea','#e9f0fc','#e9f0fc'][i]
        rects.append(f'<rect x="{x}" y="{y}" width="290" height="66" rx="9" fill="{fill}" stroke="#aebfce"/><text x="{x+15}" y="{y+22}" font-size="11" fill="#596a7b">{group}</text><text x="{x+15}" y="{y+45}" font-size="14" fill="#17314a">{label}</text>')
    # Traversal is explicitly numbered, keeping boundaries readable on small screens.
    for i in range(4):
        x=18+(i%2)*310;y=33+(i//2)*92
        rects.append(f'<circle cx="{x}" cy="{y}" r="11" fill="#17314a"/><text x="{x}" y="{y+4}" text-anchor="middle" font-size="12" fill="white">{i+1}</text>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 620 206" role="img" aria-label="'+title+'"><rect width="620" height="206" fill="white"/><text x="12" y="18" font-family="sans-serif" font-size="15" font-weight="bold">'+title+'</text><g font-family="sans-serif">'+''.join(rects)+'</g></svg>'


# Return the PDF equivalent as a ReportLab vector Drawing, with selectable text.
# Use the same two mapping choices and electronic/candidate-photonic boundaries
# as diagram_svg. Required report fonts are registered by build_pdf before use.
def draw_diagram(kind):
    # PDF uses ReportLab primitives; no rasterized diagram text.
    from reportlab.graphics.shapes import Drawing,Rect,String
    labels=(['Gather current pairs','Encode / difference / read','Sign and tie rule','Exchange; next active layer']
            if kind=='bitonic' else ['Gather all unordered pairs','Encode / difference / read','Sign and rank sums','Validate; place original records'])
    d=Drawing(475,140)
    for i,label in enumerate(labels):
        x=(i%2)*245;y=78-(i//2)*70
        d.add(Rect(x,y,230,55,rx=7,ry=7,fillColor=colors.HexColor('#e1f3ea' if i==1 else '#e9f0fc'),strokeColor=colors.HexColor('#b2c5d2')))
        d.add(String(x+12,y+34,f'{i+1}. '+('Candidate photonic path' if i==1 else 'Electronic'),fontName='DV-Bold',fontSize=8.5))
        d.add(String(x+12,y+15,label,fontName='DV',fontSize=8.3))
    return d


# Register bundled fonts, render a front section and new page descriptions,
# and insert the pre-existing historical_foundation.pdf between them.
# Find chapter pages from rendered text, replace the one-page contents placeholder,
# add footer/page numbers/bookmarks/metadata, and save the report under reports.
# Return the final page count. Missing chapter headings fail instead of producing
# guessed page references. This overwrites the dated report, so it is not run
# merely to validate a comments-only code change.
def build_pdf():
    pdfmetrics.registerFont(TTFont('DV',str(ASSET/'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('DV-Bold',str(ASSET/'DejaVuSans-Bold.ttf')))
    pdfmetrics.registerFontFamily('DV',normal='DV',bold='DV-Bold',italic='DV',boldItalic='DV-Bold')
    styles={
        'p':ParagraphStyle('p',fontName='DV',fontSize=9.35,leading=14,spaceAfter=10,textColor=colors.HexColor('#25364a')),
        'h':ParagraphStyle('h',fontName='DV-Bold',fontSize=12,leading=16,spaceBefore=7,spaceAfter=8,keepWithNext=True,textColor=colors.HexColor('#155b78')),
        'title':ParagraphStyle('title',fontName='DV-Bold',fontSize=19,leading=24,spaceAfter=17,textColor=colors.HexColor('#155b78')),
        'eq':ParagraphStyle('eq',fontName='DV',fontSize=10,leading=16,spaceBefore=7,spaceAfter=15,backColor=colors.HexColor('#edf4f8'),borderPadding=8),
        'cell':ParagraphStyle('cell',fontName='DV',fontSize=8,leading=11.5),
        'code':ParagraphStyle('code',fontName='Courier',fontSize=8,leading=12,backColor=colors.HexColor('#f0f4f8'),borderPadding=8,spaceAfter=15)}
    # Convert one string to a ReportLab Paragraph using a named local style.
    # Normalize Unicode dash variants for this report font/layout path; existing
    # supported inline markup is retained. The function returns a flowable, not a page.
    def par(s,sty='p'):return Paragraph(str(s).replace('−','-').replace('—','-').replace('–','-'),styles[sty])
    # Dispatch one tagged content tuple into a LIST of ReportLab flowables.
    # Preserve figure aspect ratio, repeat table headers on overflow, and use vector
    # diagrams. Table cells are paragraph objects so long text wraps within columns.
    # Unknown block types raise ValueError rather than disappearing from the report.
    def render_block(b):
        typ=b[0]
        if typ in ('p','h','eq'):return [par(b[1],typ)]
        if typ=='code':return [Preformatted(b[1],styles['code'])]
        if typ=='diagram':return [draw_diagram(b[1]),Spacer(1,8)]
        if typ=='picture':
            from PIL import Image as PILImage
            w,h=PILImage.open(OUT/b[1]).size
            return [Image(str(OUT/b[1]),width=475,height=475*h/w),Spacer(1,10)]
        if typ=='table':
            heads,rows,widths=b[1:]
            if widths is None:widths=[475/len(heads)]*len(heads)
            cells=[[par('<b>'+str(x)+'</b>','cell') for x in heads]]+[[par(x,'cell') for x in row] for row in rows]
            t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dfebf4')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f4f7fa')]),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,-1),.35,colors.HexColor('#d5e1eb'))]))
            return [t,Spacer(1,12)]
        raise ValueError(typ)
    # Render an ordered list of page descriptions into an in-memory PDF document.
    # Insert explicit page breaks between descriptions; flowables may still overflow.
    # Use fixed A4 dimensions/margins and return a PyMuPDF document for composition.
    # This helper is reused for front matter, tail chapters and the final contents page.
    def make_pages(pages):
        flow=[]
        for i,pg in enumerate(pages):
            if i:flow.append(PageBreak())
            flow.append(par(pg['title'],'title'))
            for b in pg['blocks']:flow.extend(render_block(b))
        bio=io.BytesIO()
        SimpleDocTemplate(bio,pagesize=(595.2756,841.8898),leftMargin=60,rightMargin=60,topMargin=54,bottomMargin=62).build(flow)
        return fitz.open(stream=bio.getvalue(),filetype='pdf')
    front=[
        {'title':'From optical sorting complexity to hybrid photonic mappings','blocks':[
            h("Master's thesis: research-phase documentation"),p('Bharadwaj Srikumar | Revision 6 | 2 October 2026'),
            eq('C = (T, S, H, D)<br/>Source-grounded architecture comparison<br/>Explicit 4-bit and 8-bit numerical evaluation'),
            p('This document preserves the established historical-model comparison and the four-parameter derivations for five optical/hybrid sorting architectures. It updates the modern bitonic/rank mapping, validation, numerical assumptions and results using the protocol agreed on 2 October 2026.'),
            h('Current milestone'),p('216 configurations; 216,000 architecture executions; 24,000 generated input arrays. Every ideal case sorts correctly and stably. Finite signed-output resolution causes false ties, while inconsistent pair decisions can invalidate ranks.'),
            p('The study supports thesis registration through a reproducible comparison and explicit hardware questions. Q.ANT device execution, calibrated optical cascades and a complete energy-efficiency verdict remain future work.'),
            p('This revision supersedes the earlier precision sweep. Ranges are now 0..15 and 0..255, input errors are rejected, and the two quantizer widths are separate configuration fields.') ]},
        {'title':'Contents','blocks':[p('Contents are generated after pagination.')]},
        {'title':'1. Executive research position','blocks':[
            p('The thesis asks when a photonic/hybrid sorting mapping makes sense under explicit correctness, resource and execution requirements. It does not assume an advantage over digital hardware.'),
            table(['Question','Current answer'],[
                ['What has been validated?','Selected source equations and examples; ideal functional behavior; quantizer controls; a complete new 4/8-bit sweep.'],
                ['What are the modern mappings?','Pair differences plus electronic compare-exchange for bitonic; pair differences plus electronic ranks and placement for rank.'],
                ['Where do they fail?','Adjacent keys may round to the same difference code; noise changes decisions; rank can develop collisions.'],
                ['What remains a hardware question?','Matrix dimensions, sign accuracy, transfers, nonlinear functions, optical chaining and regeneration.']]),
            p('Beyette and Desmulliez are retained as separate source architectures. Under the shared numerical model they execute the same fixed-shuffle schedule and receive identical comparison-error streams. Their equal precision results therefore do not distinguish physical devices.'),
            p('The numerical evidence compares two operating scenarios: 4-bit keys with 4-bit input/output conversion, and 8-bit keys with 8-bit input/output conversion. Domain size changes with precision. A future controlled sweep should hold keys fixed while varying converter settings independently.'),
            p('The preceding theoretical chapters are preserved. Subsequent numerical chapters and results are replaced, rather than mixing old 6..9-bit results with the new protocol.') ]}
    ]
    document=make_pages(front)
    historical=fitz.open(ASSET/'historical_foundation.pdf');document.insert_pdf(historical)
    tail=make_pages(PAGES);document.insert_pdf(tail)
    # Find each chapter start from its actual rendered title; no hard-coded page guesses.
    titles=['1. Executive research position','2. Concepts needed to read the study','3. The four parameters: T, S, H and D','4. Historical models and their relationship to C','5. Five sorters compared with C=(T,S,H,D)','6. Why bitonic versus rank is the focused thesis comparison','7. Q.ANT: what its capabilities mean for sorting','8. One difference operation, two sorting mappings','9. What was validated against the papers','10. The agreed experimental protocol','11. Results: what the new run establishes','12. Next experiments and hardware questions','13. Thesis registration: a concrete research goal','14. Reproduce and inspect the evaluation','15. Glossary and evidence boundary']
    # Resolve the table of contents from the actual composed PDF, including the
    # inserted historical pages. Whitespace normalization makes text matching robust
    # to line wrapping; every expected chapter must still be found.
    normalized=[' '.join(pg.get_text().split()) for pg in document]
    toc=[]
    for title in titles:
        matches=[i for i,t in enumerate(normalized) if ' '.join(title.split()) in t]
        if not matches:raise AssertionError('Missing chapter '+title)
        toc.append([title,str(matches[0]+1)])
    toc_pdf=make_pages([{'title':'Contents','blocks':[table(['Chapter','Page'],toc,[430,45]),p('Charts and exact counts are rebuilt from the saved 2 October evaluation. Historical foundation and hardware evidence retain their dated source boundaries.')]}])
    assert len(toc_pdf)==1
    document.delete_page(1);document.insert_pdf(toc_pdf,start_at=1)
    for i,pg in enumerate(document):
        pg.draw_line((60,789),(535,789),color=(.82,.87,.91),width=.5)
        pg.insert_text((60,805),'APC sorting | Research-phase documentation | Revision 6 | 2 October 2026',fontname='helv',fontsize=7.2,color=(.3,.39,.46))
        pg.insert_text((525,805),str(i+1),fontname='helv',fontsize=8,color=(.3,.39,.46))
    document.set_toc([[1,title,int(num)] for title,num in toc])
    document.set_metadata({'title':'APC Thesis Research Phase Documentation - Revision 6','author':'Bharadwaj Srikumar','subject':'Explicit 4-bit and 8-bit sorting evaluation','keywords':'photonic, sorting, bitonic, rank, quantization, Q.ANT'})
    target=OUT/'APC_Thesis_Research_Phase_Documentation.pdf'
    document.save(target,garbage=4,deflate=True)
    return len(document)


# Convert one content tuple to an HTML fragment, preserving the shared report
# structure. Convert ReportLab link markup to anchors; escape literal code blocks.
# Embed figure bytes as base64 so the generated guide works offline.
# Other prose/table fields are trusted authored report content, not arbitrary
# untrusted user HTML. Unknown tags raise ValueError like the PDF dispatcher.
def block_html(b):
    typ=b[0]
    if typ in ('p','h','eq'):
        text=re.sub(r'<link href="([^"]+)"[^>]*>(.*?)</link>',r'<a href="\1">\2</a>',b[1])
        return f'<h3>{text}</h3>' if typ=='h' else f'<div class="equation">{text}</div>' if typ=='eq' else f'<p>{text}</p>'
    if typ=='code':return '<pre><code>'+html.escape(b[1])+'</code></pre>'
    if typ=='table':return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+str(x)+'</th>' for x in b[1])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(x)+'</td>' for x in row)+'</tr>' for row in b[2])+'</tbody></table></div>'
    if typ=='picture':return '<img class="figure" alt="Saved precision results" src="data:image/png;base64,'+base64.b64encode((OUT/b[1]).read_bytes()).decode()+'">'
    if typ=='diagram':return diagram_svg(b[1])
    raise ValueError(typ)


# Read report_template.html and replace its named @@...@@ placeholders with
# saved rows, generated method sections, base64 figures/CSV, and SVG diagrams.
# Escape closing-script-like sequences in embedded JSON to keep it inside its
# data script element. The browser only explores these saved rows; it does not
# rerun experiments. Write the self-contained historical HTML guide under reports.
def build_html():
    template=(ASSET/'report_template.html').read_text()
    methods=''.join('<details><summary>'+pg['title']+'</summary><div class="detail-body">'+''.join(block_html(b) for b in pg['blocks'])+'</div></details>' for pg in PAGES if not pg['title'].startswith('11.'))
    image4=base64.b64encode((OUT/'precision_4bit.png').read_bytes()).decode()
    image8=base64.b64encode((OUT/'precision_8bit.png').read_bytes()).decode()
    text=template.replace('@@ROWS@@',json.dumps(ROWS).replace('</',r'<\/')).replace('@@METHODS@@',methods).replace('@@FIG4@@',image4).replace('@@FIG8@@',image8).replace('@@CSV@@',base64.b64encode((R/'precision.csv').read_bytes()).decode()).replace('@@BITONIC@@',diagram_svg('bitonic')).replace('@@RANK@@',diagram_svg('rank'))
    (OUT/'APC_Thesis_Registration_Visual_Guide.html').write_text(text)


# Direct execution starts this file's command-line/test entry point.
# Importing helpers does not run THIS block; the module reading guide
# identifies any other top-level file loading or writing separately.
if __name__=='__main__':
    figures();count=build_pdf();build_html()
    print(f'Generated HTML report and {count}-page updated PDF from {len(ROWS)} saved rows.')
