class ArcanaException(Exception):

    @property
    def msg(self):
        return self.args[0]

    @msg.setter
    def msg(self, msg):
        self.args = (msg,) + self.args[1:]


class ArcanaError(ArcanaException):
    pass


class ArcanaNotBoundToAnalysisError(ArcanaError):
    pass


class ArcanaVersionError(ArcanaError):
    pass


class ArcanaRequirementNotFoundError(ArcanaVersionError):
    pass


class ArcanaVersionNotDetectableError(ArcanaVersionError):
    pass


class ArcanaEnvModuleNotLoadedError(ArcanaError):
    pass


class ArcanaMissingInputError(ArcanaException):
    pass


class ArcanaProtectedOutputConflictError(ArcanaError):
    pass


class ArcanaCantPickleAnalysisError(ArcanaError):
    pass


class ArcanaRepositoryError(ArcanaError):
    pass


class ArcanaUsageError(ArcanaError):
    pass


class ArcanaDesignError(ArcanaError):
    pass


class NamedArcanaError(ArcanaError):

    def __init__(self, name, msg):
        super(NamedArcanaError, self).__init__(msg)
        self.name = name


class ArcanaNameError(NamedArcanaError):
    pass


class ArcanaIndexError(ArcanaError):

    def __init__(self, index, msg):
        super(ArcanaIndexError, self).__init__(msg)
        self.index = index


class ArcanaMissingDataException(ArcanaUsageError):
    pass


class ArcanaDataNotDerivedYetError(NamedArcanaError, ArcanaDesignError):
    pass


class ArcanaInputError(ArcanaUsageError):
    pass


class ArcanaInputMissingMatchError(ArcanaInputError):
    pass


class ArcanaOutputNotProducedException(ArcanaException):
    """
    Raised when a given spec is not produced due to switches and inputs
    provided to the analysis
    """


class ArcanaInsufficientRepoDepthError(ArcanaError):
    pass


class ArcanaFileFormatError(ArcanaError):
    pass


class ArcanaFilesetNotCachedException(ArcanaException):
    pass


class NoMatchingPipelineException(ArcanaException):
    pass


class ArcanaModulesError(ArcanaError):
    pass


class ArcanaModulesNotInstalledException(ArcanaException):
    pass


class ArcanaJobSubmittedException(ArcanaException):
    """
    Signifies that a pipeline has been submitted to a scheduler and
    a return value won't be returned.
    """


class ArcanaNoRunRequiredException(ArcanaException):
    """
    Used to signify when a pipeline doesn't need to be run as all
    required outputs are already present in the repository
    """


class ArcanaFileFormatClashError(ArcanaError):
    """
    Used when two mismatching data formats are registered with the same
    name or extention
    """


class ArcanaNoConverterError(ArcanaError):
    "No converters exist between formats"


class ArcanaConverterNotAvailableError(ArcanaError):
    "The converter required to convert between formats is not "
    "available"


class ArcanaReprocessException(ArcanaException):
    pass


class ArcanaWrongRepositoryError(ArcanaError):
    pass


class ArcanaIvalidParameterError(ArcanaError):
    pass
