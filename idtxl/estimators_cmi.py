import jpype as jp
import numpy as np
import pyinfo
import utils as utils
import neighbour_search_opencl as nsocl
from scipy.special import digamma


def opencl_kraskov(self, var1, var2, conditional, opts=None):
    """Calculate conditional mutual infor using opencl Kraskov implementation.

    Calculate the conditional mutual information between three variables using
    an opencl-based Kraskov type 1 estimator. References:

        Kraskov, A., Stögbauer, H., & Grassberger, P. (2004). Estimating mutual
        information. Physical review E, 69(6), 066138.

    This function is ment to be imported into the set_estimator module and used
    as a method in the Estimator_cmi class.

    Args:
        self : instance of Estimator_cmi
        var1 : numpy array
            realisations of the first random variable, where dimensions are
            realisations x variable dimension
        var2: numpy array
            realisations of the second random variable
        conditional : numpy array
            realisations of the random variable for conditioning
        opts : dict [optional]
            sets estimation parameters:
            'kraskov_k' - no. nearest neighbours for KNN search (default=4)
            'theiler_t' - no. next temporal neighbours ignored in KNN and
            range searches (default='ACT', the autocorr. time of the target)
            'noise_level' - random noise added to the data (default=1e-8)

    Returns:
        float
            conditional mutual information

    Note:
        The Theiler window ignores trial boundaries. The CMI estimator does add
        noise to the data as a default. To make analysis runs replicable set
        noise_level to 0.
    """
    if opts is None:
        opts = {}
    try:
        kraskov_k = int(opts['kraskov_k'])
    except KeyError:
        kraskov_k = int(4)
    try:
        theiler_t = int(opts['theiler_t'])
    except KeyError:
        theiler_t = int(0)
    try:
        noise_level = int(opts['noise_level'])
    except KeyError:
        noise_level = 1e-8
    try:
        gpuid = int(opts['gpuid'])
    except KeyError:
        gpuid = int(0)

    try:
        nchunkspergpu = int(opts['nchunkspergpu'])
    except KeyError:
        nchunkspergpu = int(1)

    var1 += np.random.normal(size=var1.shape) * noise_level
    var2 += np.random.normal(size=var2.shape) * noise_level
    conditional += np.random.normal(size=conditional.shape) * noise_level

    # build pointsets - Note we assume that pointsets are given in IDTxl conv.
    # 1. full space
    pointset_full_space = np.hstack((var1, var2, conditional))
    pointset_full_space = pointset_full_space.astype('float32')
    n_dim_full = pointset_full_space.shape[1]
    # 2. conditional variable only
    pointset_conditional = np.array(conditional)
    pointset_conditional = pointset_conditional.astype('float32')
    n_dim_conditional = pointset_conditional.shape[1]
    print("n_dim_conditional is: {0}".format(n_dim_conditional))
    # 3. pointset variable 1 and conditional
    pointset_var1_conditional = np.hstack((var1, conditional))
    pointset_var1_conditional = pointset_var1_conditional.astype('float32')
    n_dim_var1_conditional = pointset_var1_conditional.shape[1]
    # 4. pointset variable 2 and conditional
    pointset_var2_conditional = np.hstack((var2, conditional))
    pointset_var2_conditional = pointset_var2_conditional.astype('float32')
    n_dim_var2_conditional = pointset_var2_conditional.shape[1]

    signallengthpergpu = pointset_full_space.shape[0]

#    print("working with signallength: %i" %signallengthpergpu)
    chunksize = signallengthpergpu / nchunkspergpu # TODO check for integer result

    indexes, distances = nsocl.knn_search(pointset_full_space, n_dim_full,
                                          kraskov_k, theiler_t, nchunkspergpu,
                                          gpuid)
#    print("indexes:")
#    print(indexes)
#    print("distances")
#    print(distances)
#    print("shape of distance matrix: ")
#    print(distances.shape)
#    # define the search radii as the distances to the kth (=last) neighbours
    radii = distances[distances.shape[0]-1, :]
#    print(radii)

    # get neighbour counts in ranges
    count_conditional = nsocl.range_search(pointset_conditional,
                                           n_dim_conditional, radii,
                                           theiler_t, nchunkspergpu, gpuid)

    # get neighbour counts in ranges
    count_var1_conditional = nsocl.range_search(pointset_var1_conditional,
                                                n_dim_var1_conditional,
                                                radii, theiler_t,
                                                nchunkspergpu, gpuid)

    # get neighbour counts in ranges
    count_var2_conditional = nsocl.range_search(pointset_var2_conditional,
                                                n_dim_var2_conditional,
                                                radii, theiler_t,
                                                nchunkspergpu, gpuid)

    cmi = (digamma(kraskov_k) + np.mean(digamma(count_conditional + 1) -
           digamma(count_var1_conditional + 1) -
           digamma(count_var2_conditional + 1)))
    return cmi


def jidt_kraskov(self, var1, var2, conditional, opts=None):
    """Calculate conditional mutual infor with JIDT's Kraskov implementation.

    Calculate the conditional mutual information between three variables. Call
    JIDT via jpype and use the Kraskov 1 estimator. If no conditional is given
    (is None), the function returns the mutual information between var1 and
    var2. References:

        Kraskov, A., Stögbauer, H., & Grassberger, P. (2004). Estimating mutual
        information. Physical Review E, 69(6), 066138.

        Lizier, Joseph T. (2014). JIDT: an information-theoretic toolkit for
        studying the dynamics of complex systems. Front. Robot. AI, 1(11).

    This function is ment to be imported into the set_estimator module and used
    as a method in the Estimator_cmi class.

    Args:
        self : instance of Estimator_cmi
        var1 : numpy array
            realisations of the first random variable, where dimensions are
            realisations x variable dimension
        var2 : numpy array
            realisations of the second random variable
        conditional : numpy array
            realisations of the random variable for conditioning
        opts : dict [optional]
            sets estimation parameters:
            'kraskov_k' - no. nearest neighbours for KNN search (default=4)
            'normalise' - z-standardise data (default=False)
            'theiler_t' - no. next temporal neighbours ignored in KNN and
            range searches (default='ACT', the autocorr. time of the target)
            'noise_level' - random noise added to the data (default=1e-8)
            'num_threads' - no. CPU threads used for estimation
            (default='USE_ALL', this uses all available cores on the machine!)

    Returns:
        float
            conditional mutual information

    Note:
        Some technical details: JIDT normalises over realisations, IDTxl
        normalises over raw data once, outside the CMI calculator to save
        computation time. The Theiler window ignores trial boundaries. The
        CMI estimator does add noise to the data as a default. To make analysis
        runs replicable set noise_level to 0.
    """
    if opts is None:
        opts = {}
    try:
        kraskov_k = str(opts['kraskov_k'])
    except KeyError:
        kraskov_k = str(4)
    try:
        if opts['normalise']:
            normalise = 'true'
        else:
            normalise = 'false'
    except KeyError:
        normalise = 'false'
    try:
        theiler_t = str(opts['theiler_t'])
    except KeyError:
        theiler_t = str(utils.autocorrelation(var1))  # TODO this is no good bc we don't know if var1 is the target
    try:
        noise_level = str(opts['noise_level'])
    except KeyError:
        noise_level = str(1e-8)
    try:
        num_threads = str(opts['num_threads'])
    except KeyError:
        num_threads = 'USE_ALL'
    try:
        debug = opts['debug']
    except KeyError:
        debug = False

    jarLocation = 'infodynamics.jar'
    if not jp.isJVMStarted():
        jp.startJVM(jp.getDefaultJVMPath(), '-ea', ('-Djava.class.path=' +
                    jarLocation))

    calcClass = (jp.JPackage('infodynamics.measures.continuous.kraskov').
                 ConditionalMutualInfoCalculatorMultiVariateKraskov1)
    calc = calcClass()
    calc.setProperty('NORMALISE', normalise)
    calc.setProperty('k', kraskov_k)
    calc.setProperty('DYN_CORR_EXCL', theiler_t)
    calc.setProperty('NOISE_LEVEL_TO_ADD', noise_level)
    calc.setProperty('NUM_THREADS', num_threads)
    calc.setDebug(debug)

    if conditional is None:
        cond_dim = 0
    else:
        cond_dim = conditional.shape[1]
        assert(conditional.size != 0), 'Conditional Array is empty.'
    calc.initialise(var1.shape[1], var2.shape[1], cond_dim)
    calc.setObservations(var1, var2, conditional)
    return calc.computeAverageLocalOfObservations()


def pyinfo_kraskov(self, var1, var2, conditional, knn):
    """Return the conditional mutual information calculated by the pyinfo module
    using the Kraskov estimator."""

    return pyinfo.cmi_kraskov(var1, var2, conditional)
