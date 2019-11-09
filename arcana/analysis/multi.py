from past.builtins import basestring
from builtins import object
from arcana.exceptions import (
    ArcanaMissingDataException, ArcanaNameError)
from arcana.exceptions import ArcanaUsageError
from .base import Analysis, AnalysisMetaClass


class MultiAnalysis(Analysis):
    """
    Abstract base class for all studies that combine multiple studies
    into a "multi-analysis".

    Parameters
    ----------
    name : str
        The name of the combined analysis.
    repository : Repository
        An Repository object that provides access to a DaRIS, XNAT or
        local file system
    processor : Processor
        The processor the processes the derived data when demanded
    inputs : Dict[str, Fileset|Field]
        A dict containing the a mapping between names of analysis data_specs
        and existing filesets (typically primary from the scanner but can
        also be replacements for generated data_specs)
    parameters : List[Parameter] | Dict[str, (int|float|str)]
        Parameters that are passed to pipelines when they are constructed
        either as a dictionary of key-value pairs or as a list of
        'Parameter' objects. The name and dtype must match ParamSpecs in
        the _param_spec class attribute (see 'add_param_specs').
    subject_ids : List[(int|str)]
        List of subject IDs to restrict the analysis to
    visit_ids : List[(int|str)]
        List of visit IDs to restrict the analysis to
    check_inputs : bool
        Whether to check the inputs to see if any acquired filesets
        are missing
    reprocess : bool
        Whether to reprocess fileset|fields that have been created with
        different parameters and/or pipeline-versions. If False then
        and exception will be thrown if the repository already contains
        matching filesets|fields created with different parameters.

    Class Attrs
    -----------
    add_subcomp_specs : list[SubCompSpec]
        Subclasses of MultiAnalysis typically have a 'add_subcomp_specs'
        class member, which defines the sub-studies that make up the
        combined analysis and the mapping of their fileset names. The key
        of the outer dictionary will be the name of the sub-analysis, and
        the value is a tuple consisting of the class of the sub-analysis
        and a map of fileset names from the combined analysis to the
        sub-analysis e.g.

            add_subcomp_specs = [
                SubCompSpec('t1_analysis', T1wAnalysis, {'magnitude': 't1'}),
                SubCompSpec('t2_analysis', T2wAnalysis, {'magnitude': 't2'})]

            add_data_specs = [
                FilesetSpec('t1', text_format'),
                FilesetSpec('t2', text_format')]
    add_data_specs : List[FilesetSpec|FieldSpec]
        Add's that data specs to the 'data_specs' class attribute,
        which is a dictionary that maps the names of filesets that are
        used and generated by the analysis to FilesetSpec objects.
    add_param_specs : List[ParamSpec]
        Default parameters for the class
    """

    _subcomp_specs = {}

    implicit_cls_attrs = Analysis.implicit_cls_attrs + ['_subcomp_specs']

    def __init__(self, name, repository, processor, inputs,
                 parameters=None, **kwargs):
        try:
            # This works for PY3 as the metaclass inserts it itself if
            # it isn't provided
            metaclass = type(self).__dict__['__metaclass__']
            if not issubclass(metaclass, MultiAnalysisMetaClass):
                raise KeyError
        except KeyError:
            raise ArcanaUsageError(
                "Need to set MultiAnalysisMetaClass (or sub-class) as "
                "the metaclass of all classes derived from "
                "MultiAnalysis")
        super(MultiAnalysis, self).__init__(
            name, repository, processor, inputs, parameters=parameters,
            **kwargs)
        self._substudies = {}
        for subcomp_spec in self.subcomp_specs():
            subcomp_cls = subcomp_spec.analysis_class
            # Map inputs, data_specs to the subcomp
            mapped_inputs = {}
            for data_name in subcomp_cls.data_spec_names():
                mapped_name = subcomp_spec.map(data_name)
                if mapped_name in self.input_names:
                    mapped_inputs[data_name] = self.input(mapped_name)
                else:
                    try:
                        inpt = self.spec(mapped_name)
                    except ArcanaMissingDataException:
                        pass
                    else:
                        if inpt.derived:
                            mapped_inputs[data_name] = inpt
            # Map parameters to the subcomp
            mapped_parameters = {}
            for param_name in subcomp_cls.param_spec_names():
                mapped_name = subcomp_spec.map(param_name)
                parameter = self._get_parameter(mapped_name)
                mapped_parameters[param_name] = parameter
            # Create sub-analysis
            subcomp = subcomp_spec.analysis_class(
                name + '_' + subcomp_spec.name,
                repository, processor, mapped_inputs,
                parameters=mapped_parameters, enforce_inputs=False,
                subject_ids=self.subject_ids, visit_ids=self.visit_ids,
                clear_caches=False)
            # Append to dictionary of substudies
            if subcomp_spec.name in self._substudies:
                raise ArcanaNameError(
                    subcomp_spec.name,
                    "Duplicate sub-analysis names '{}'"
                    .format(subcomp_spec.name))
            self._substudies[subcomp_spec.name] = subcomp

    @property
    def substudies(self):
        return iter(self._substudies.values())

    @property
    def subcomp_names(self):
        return iter(self._substudies.keys())

    def subcomp(self, name):
        try:
            return self._substudies[name]
        except KeyError:
            raise ArcanaNameError(
                name,
                "'{}' not found in sub-studes ('{}')"
                .format(name, "', '".join(self._substudies)))

    @classmethod
    def subcomp_spec(cls, name):
        try:
            return cls._subcomp_specs[name]
        except KeyError:
            raise ArcanaNameError(
                name,
                "'{}' not found in sub-studes ('{}')"
                .format(name, "', '".join(cls._subcomp_specs)))

    @classmethod
    def subcomp_specs(cls):
        return iter(cls._subcomp_specs.values())

    @classmethod
    def subcomp_spec_names(cls):
        return iter(cls._subcomp_specs.keys())

    def __repr__(self):
        return "{}(name='{}')".format(
            self.__class__.__name__, self.name)

    @classmethod
    def translate(cls, subcomp_name, pipeline_getter, pipeline_arg_names=(),
                  auto_added=False):
        """
        A method for translating pipeline constructors from a sub-analysis to
        the namespace of a multi-analysis. Returns a new method that calls the
        sub-analysis pipeline constructor with appropriate keyword arguments

        Parameters
        ----------
        subcomp_name : str
            Name of the sub-analysis
        pipeline_getter : str
            Name of method used to construct the pipeline in the sub-analysis
        pipeline_arg_names : tuple[str]
            Names of pipeline arguments passed to the method
        auto_added : bool
            Signify that a method was automatically added by the
            MultiAnalysisMetaClass. Used in checks when pickling Analysis
            objects
        """
        assert isinstance(subcomp_name, basestring)
        assert isinstance(pipeline_getter, basestring)

        def translated_getter(self, **kwargs):
            subcomp_spec = self.subcomp_spec(subcomp_name)
            pipeline_args = {n: kwargs.pop(n) for n in pipeline_arg_names}
            # Combine mapping of names of sub-analysis specs with
            return getattr(self.subcomp(subcomp_name), pipeline_getter)(
                prefix=subcomp_name + '_',
                input_map=subcomp_spec.name_map,
                output_map=subcomp_spec.name_map,
                analysis=self, name_maps=kwargs,
                **pipeline_args)
        # Add reduce method to allow it to be pickled
        translated_getter.auto_added = auto_added
        return translated_getter


class SubCompSpec(object):
    """
    Specify a analysis to be included in a MultiAnalysis class

    Parameters
    ----------
    name : str
        Name for the sub-analysis
    analysis_class : type (sub-classed from Analysis)
        The class of the sub-analysis
    name_map : dict[str, str]
        A mapping of fileset/field/parameter names from the sub-analysis
        namespace to the namespace of the MultiAnalysis. All data-specs
        that are not explicitly mapped are auto-translated using
        the sub-analysis prefix (name + '_').
    """

    def __init__(self, name, analysis_class, name_map=None):
        self._name = name
        self._analysis_class = analysis_class
        # Fill fileset map with default values before overriding with
        # argument provided to constructor
        self._name_map = name_map if name_map is not None else {}

    @property
    def name(self):
        return self._name

    def __repr__(self):
        return "{}(name='{}', cls={}, name_map={}".format(
            type(self).__name__, self.name, self.analysis_class,
            self._name_map)

    @property
    def analysis_class(self):
        return self._analysis_class

    @property
    def name_map(self):
        nmap = dict((s.name, self.apply_prefix(s.name))
                    for s in self.auto_data_specs)
        nmap.update(self._name_map)
        return nmap

    def map(self, name):
        try:
            return self._name_map[name]
        except KeyError:
            if name not in self.analysis_class.spec_names():
                raise ArcanaNameError(
                    name,
                    ("'{}' doesn't match any filesets, fields, parameters "
                     + "in the analysis class {} ('{}')")
                    .format(name, self.name,
                            self.analysis_class.__name__,
                            "', '".join(self.analysis_class.spec_names())))
            return self.apply_prefix(name)

    def apply_prefix(self, name):
        return self.name + '_' + name

    @property
    def auto_data_specs(self):
        """
        Data specs in the sub-analysis class that are not explicitly provided
        in the name map
        """
        for spec in self.analysis_class.data_specs():
            if spec.name not in self._name_map:
                yield spec

    @property
    def auto_param_specs(self):
        """
        Parameter pecs in the sub-analysis class that are not explicitly
        provided in the name map
        """
        for spec in self.analysis_class.param_specs():
            if spec.name not in self._name_map:
                yield spec


class MultiAnalysisMetaClass(AnalysisMetaClass):
    """
    Metaclass for "multi" analysis classes that automatically adds
    translated data specs and pipelines from sub-analysis specs if they
    are not explicitly mapped in the spec.
    """

    def __new__(metacls, name, bases, dct):  # @NoSelf @UnusedVariable
        if not any(issubclass(b, MultiAnalysis) for b in bases):
            raise ArcanaUsageError(
                "MultiAnalysisMetaClass can only be used for classes that "
                "have MultiAnalysis as a base class")
        try:
            add_subcomp_specs = dct['add_subcomp_specs']
        except KeyError:
            add_subcomp_specs = dct['add_subcomp_specs'] = []
        dct['_subcomp_specs'] = subcomp_specs = {}
        for base in reversed(bases):
            try:
                subcomp_specs.update(
                    (d.name, d) for d in base.subcomp_specs())
            except AttributeError:
                pass
        subcomp_specs.update(
            (s.name, s) for s in add_subcomp_specs)
        if '__metaclass__' not in dct:
            dct['__metaclass__'] = metacls
        cls = AnalysisMetaClass(name, bases, dct)
        # Loop through all data specs that haven't been explicitly
        # mapped and add a data spec in the multi class.
        for subcomp_spec in list(subcomp_specs.values()):
            # Map data specs
            for data_spec in subcomp_spec.auto_data_specs:
                trans_sname = subcomp_spec.apply_prefix(
                    data_spec.name)
                if trans_sname not in cls.data_spec_names():
                    initkwargs = data_spec.initkwargs()
                    initkwargs['name'] = trans_sname
                    if data_spec.derived:
                        trans_pname = subcomp_spec.apply_prefix(
                            data_spec.pipeline_getter)
                        initkwargs['pipeline_getter'] = trans_pname
                        # Check to see whether pipeline has already been
                        # translated or always existed in the class (when
                        # overriding default parameters for example)
                        if not hasattr(cls, trans_pname):
                            setattr(cls, trans_pname,
                                    MultiAnalysis.translate(
                                        subcomp_spec.name,
                                        data_spec.pipeline_getter,
                                        pipeline_arg_names=(
                                            data_spec.pipeline_arg_names),
                                        auto_added=True))
                    trans_data_spec = type(data_spec)(**initkwargs)
                    # Allow the default input (e.g. an atlas) to translate
                    # any parameter names it needs to use
                    if not data_spec.derived and data_spec.default is not None:
                        try:
                            trans_data_spec.default.translate(subcomp_spec)
                        except AttributeError:
                            pass
                    cls._data_specs[trans_sname] = trans_data_spec
            # Map parameter specs
            for param_spec in subcomp_spec.auto_param_specs:
                trans_sname = subcomp_spec.apply_prefix(
                    param_spec.name)
                if trans_sname not in cls.param_spec_names():
                    renamed_spec = param_spec.renamed(trans_sname)
                    cls._param_specs[
                        renamed_spec.name] = renamed_spec
        # Check all names in name-map correspond to data or parameter
        # specs
        for subcomp_spec in list(subcomp_specs.values()):
            local_spec_names = list(
                subcomp_spec.analysis_class.spec_names())
            for (local_name,
                 global_name) in subcomp_spec._name_map.items():
                if local_name not in local_spec_names:
                    raise ArcanaUsageError(
                        "'{}' in name-map for '{}' sub analysis spec in {}"
                        "MultiAnalysis class does not name a spec in {} "
                        "class:\n{}"
                        .format(local_name, subcomp_spec.name,
                                name, subcomp_spec.analysis_class,
                                '\n'.join(local_spec_names)))
                if global_name not in cls.spec_names():
                    raise ArcanaUsageError(
                        "'{}' in name-map for '{}' sub analysis spec in {}"
                        "MultiAnalysis class does not name a spec:\n{}"
                        .format(global_name, subcomp_spec.name, name,
                                '\n'.join(cls.spec_names())))
        return cls
