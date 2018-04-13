from abc import ABCMeta, abstractmethod
from itertools import chain
from nipype.interfaces.base import (
    traits, TraitedSpec, DynamicTraitedSpec, Undefined, File, Directory,
    BaseInterface)
from nianalysis.nodes import Node
from nianalysis.dataset import (
    Dataset, DatasetSpec, FieldSpec, BaseField, BaseDataset)
from nianalysis.exceptions import NiAnalysisError
from nianalysis.utils import PATH_SUFFIX, FIELD_SUFFIX

PATH_TRAIT = traits.Either(File(exists=True), Directory(exists=True))
FIELD_TRAIT = traits.Either(traits.Int, traits.Float, traits.Str)
MULTIPLICITIES = ('per_session', 'per_subject', 'per_visit', 'per_project')


class Archive(object):
    """
    Abstract base class for all Archive systems, DaRIS, XNAT and local file
    system. Sets out the interface that all Archive classes should implement.
    """

    __metaclass__ = ABCMeta

    @abstractmethod
    def source(self, inputs, name=None, study_name=None, **kwargs):
        """
        Returns a NiPype node that gets the input data from the archive
        system. The input spec of the node's interface should inherit from
        ArchiveSourceInputSpec

        Parameters
        ----------
        project_id : str
            The ID of the project to return the sessions for
        inputs : list(Dataset|Field)
            An iterable of nianalysis.Dataset or nianalysis.Field
            objects, which specify the datasets to extract from the
            archive system
        name : str
            Name of the NiPype node
        study_name: str
            Prefix used to distinguish datasets generated by a particular
            study. Used for processed datasets only
        """
        if name is None:
            name = "{}_source".format(self.type)
        inputs = list(inputs)  # protected against iterators
        datasets = [i for i in inputs if isinstance(i, BaseDataset)]
        fields = [i for i in inputs if isinstance(i, BaseField)]
        return Node(self.Source(study_name, datasets, fields, **kwargs),
                    name=name)

    @abstractmethod
    def sink(self, outputs, multiplicity='per_session', name=None,
             study_name=None, **kwargs):
        """
        Returns a NiPype node that puts the output data back to the archive
        system. The input spec of the node's interface should inherit from
        ArchiveSinkInputSpec

        Parameters
        ----------
        project_id : str
            The ID of the project to return the sessions for
        outputs : List(BaseFile|Field) | list(
            An iterable of nianalysis.Dataset nianalysis.Field objects,
            which specify the datasets to put into the archive system
        name : str
            Name of the NiPype node
        study_name: str
            Prefix used to distinguish datasets generated by a particular
            study. Used for processed datasets only

        """
        if name is None:
            name = "{}_{}_sink".format(self.type, multiplicity)
        outputs = list(outputs)  # protected against iterators
        if multiplicity.startswith('per_session'):
            sink_class = self.Sink
        elif multiplicity.startswith('per_subject'):
            sink_class = self.SubjectSink
        elif multiplicity.startswith('per_visit'):
            sink_class = self.VisitSink
        elif multiplicity.startswith('per_project'):
            sink_class = self.ProjectSink
        else:
            raise NiAnalysisError(
                "Unrecognised multiplicity '{}' can be one of '{}'"
                .format(multiplicity,
                        "', '".join(Dataset.MULTIPLICITY_OPTIONS)))
        datasets = [o for o in outputs if isinstance(o, BaseDataset)]
        fields = [o for o in outputs if isinstance(o, BaseField)]
        return Node(sink_class(study_name, datasets, fields, **kwargs),
                    name=name)


class BaseArchiveNode(BaseInterface):
    """
    Parameters
    ----------
    infields : list of str
        Indicates the input fields to be dynamically created

    outfields: list of str
        Indicates output fields to be dynamically created

    See class examples for usage

    """

    def __init__(self, study_name, datasets, fields):
        super(BaseArchiveNode, self).__init__()
        self._study_name = study_name
        self._datasets = datasets
        self._fields = fields

    def __eq__(self, other):
        try:
            return (self.study_name == other.study_name and
                    self.datasets == other.datasets and
                    self.fields == other.fields)
        except AttributeError:
            return False

    def __repr__(self):
        return "{}(study_name='{}', datasets={}, fields={})".format(
            type(self).__name__, self.study_name, self.datasets,
            self.fields)

    def __ne__(self, other):
        return not self == other

    def _run_interface(self, runtime, *args, **kwargs):  # @UnusedVariable
        return runtime

    @property
    def study_name(self):
        return self._study_name

    @property
    def datasets(self):
        return self._datasets

    @property
    def fields(self):
        return self._fields

    @classmethod
    def _add_trait(cls, spec, name, trait_type):
        spec.add_trait(name, trait_type)
        spec.trait_set(trait_change_notify=False, **{name: Undefined})
        # Access the trait (not sure why but this is done in add_traits
        # so I have also done it here
        getattr(spec, name)

    def prefix_study_name(self, name, is_spec=True):
        """Prepend study name if defined"""
        if is_spec:
            name = self.study_name + '_' + name
        return name


class ArchiveSourceInputSpec(DynamicTraitedSpec):
    """
    Base class for archive source input specifications. Provides a common
    interface for 'run_pipeline' when using the archive source to extract
    primary and preprocessed datasets from the archive system
    """
    subject_id = traits.Str(mandatory=True, desc="The subject ID")
    visit_id = traits.Str(mandatory=True, usedefult=True,
                            desc="The visit or processed group ID")


class ArchiveSource(BaseArchiveNode):
    """
    Parameters
    ----------
    datasets: list
        List of all datasets to be extracted from the archive
    fields: list
        List of all the fields that are to be extracted from the archive
    study_name: str
        Prefix prepended onto processed dataset "names"
    """

    output_spec = DynamicTraitedSpec
    _always_run = True

    def _outputs(self):
        outputs = super(ArchiveSource, self)._outputs()
        # Add output datasets
        for dataset in self.datasets:
            assert isinstance(dataset, BaseDataset)
            self._add_trait(outputs, dataset.name + PATH_SUFFIX,
                            PATH_TRAIT)
        # Add output fields
        for field in self.fields:
            assert isinstance(field, BaseField)
            self._add_trait(outputs, field.name + FIELD_SUFFIX,
                            field.dtype)
        return outputs


class BaseArchiveSinkSpec(DynamicTraitedSpec):
    pass


class ArchiveSinkInputSpec(BaseArchiveSinkSpec):

    subject_id = traits.Str(mandatory=True, desc="The subject ID"),
    visit_id = traits.Str(mandatory=False,
                            desc="The session or processed group ID")


class ArchiveSubjectSinkInputSpec(BaseArchiveSinkSpec):

    subject_id = traits.Str(mandatory=True, desc="The subject ID")


class ArchiveVisitSinkInputSpec(BaseArchiveSinkSpec):

    visit_id = traits.Str(mandatory=True, desc="The visit ID")


class ArchiveProjectSinkInputSpec(BaseArchiveSinkSpec):
    pass


class BaseArchiveSinkOutputSpec(DynamicTraitedSpec):

    out_files = traits.List(PATH_TRAIT, desc='Output datasets')

    out_fields = traits.List(
        traits.Tuple(traits.Str, FIELD_TRAIT), desc='Output fields')


class ArchiveSinkOutputSpec(BaseArchiveSinkOutputSpec):

    subject_id = traits.Str(desc="The subject ID")
    visit_id = traits.Str(desc="The visit ID")


class ArchiveSubjectSinkOutputSpec(BaseArchiveSinkOutputSpec):

    subject_id = traits.Str(desc="The subject ID")


class ArchiveVisitSinkOutputSpec(BaseArchiveSinkOutputSpec):

    visit_id = traits.Str(desc="The visit ID")


class ArchiveProjectSinkOutputSpec(BaseArchiveSinkOutputSpec):

    project_id = traits.Str(desc="The project ID")


class BaseArchiveSink(BaseArchiveNode):

    def __init__(self, study_name, datasets, fields):
        super(BaseArchiveSink, self).__init__(study_name, datasets,
                                              fields)
        # Add input datasets
        for dataset in datasets:
            assert isinstance(dataset, DatasetSpec)
            self._add_trait(self.inputs, dataset.name + PATH_SUFFIX,
                            PATH_TRAIT)
        # Add input fields
        for field in fields:
            assert isinstance(field, FieldSpec)
            self._add_trait(self.inputs, field.name + FIELD_SUFFIX,
                            field.dtype)


class ArchiveSink(BaseArchiveSink):

    input_spec = ArchiveSinkInputSpec
    output_spec = ArchiveSinkOutputSpec

    multiplicity = 'per_session'

    def _base_outputs(self):
        outputs = self.output_spec().get()
        outputs['subject_id'] = self.inputs.subject_id
        outputs['visit_id'] = self.inputs.visit_id
        return outputs


class ArchiveSubjectSink(BaseArchiveSink):

    input_spec = ArchiveSubjectSinkInputSpec
    output_spec = ArchiveSubjectSinkOutputSpec

    multiplicity = 'per_subject'

    def _base_outputs(self):
        outputs = self.output_spec().get()
        outputs['subject_id'] = self.inputs.subject_id
        return outputs


class ArchiveVisitSink(BaseArchiveSink):

    input_spec = ArchiveVisitSinkInputSpec
    output_spec = ArchiveVisitSinkOutputSpec

    multiplicity = 'per_visit'

    def _base_outputs(self):
        outputs = self.output_spec().get()
        outputs['visit_id'] = self.inputs.visit_id
        return outputs


class ArchiveProjectSink(BaseArchiveSink):

    input_spec = ArchiveProjectSinkInputSpec
    output_spec = ArchiveProjectSinkOutputSpec

    multiplicity = 'per_project'

    def _base_outputs(self):
        outputs = self.output_spec().get()
        return outputs


class Project(object):

    def __init__(self, subjects, visits, datasets, fields):
        self._subjects = subjects
        self._visits = visits
        self._datasets = datasets
        self._fields = fields

    @property
    def subjects(self):
        return iter(self._subjects)

    @property
    def visits(self):
        return iter(self._visits)

    @property
    def datasets(self):
        return self._datasets

    @property
    def fields(self):
        return self._fields

    @property
    def dataset_names(self):
        return (d.name for d in self.datasets)

    @property
    def field_names(self):
        return (f.name for f in self.fields)

    @property
    def data(self):
        return chain(self.datasets, self.fields)

    @property
    def data_names(self):
        return (d.name for d in self.data)

    def __eq__(self, other):
        if not isinstance(other, Project):
            return False
        return (self._subjects == other._subjects and
                self._visits == other._visits and
                self._datasets == other._datasets and
                self._fields == other._fields)

    def find_mismatch(self, other, indent=''):
        """
        Used in debugging unittests
        """
        if self != other:
            mismatch = "\n{}Project".format(indent)
        else:
            mismatch = ''
        sub_indent = indent + '  '
        if len(list(self.subjects)) != len(list(other.subjects)):
            mismatch += ('\n{indent}mismatching subject lengths '
                         '(self={} vs other={}): '
                         '\n{indent}  self={}\n{indent}  other={}'
                         .format(len(list(self.subjects)),
                                 len(list(other.subjects)),
                                 list(self.subjects),
                                 list(other.subjects),
                                 indent=sub_indent))
        else:
            for s, o in zip(self.subjects, other.subjects):
                mismatch += s.find_mismatch(o, indent=sub_indent)
        if len(list(self.visits)) != len(list(other.visits)):
            mismatch += ('\n{indent}mismatching visit lengths '
                         '(self={} vs other={}): '
                         '\n{indent}  self={}\n{indent}  other={}'
                         .format(len(list(self.visits)),
                                 len(list(other.visits)),
                                 list(self.visits),
                                 list(other.visits),
                                 indent=sub_indent))
        else:
            for s, o in zip(self.visits, other.visits):
                mismatch += s.find_mismatch(o, indent=sub_indent)
        if len(list(self.datasets)) != len(list(other.datasets)):
            mismatch += ('\n{indent}mismatching summary dataset lengths '
                         '(self={} vs other={}): '
                         '\n{indent}  self={}\n{indent}  other={}'
                         .format(len(list(self.datasets)),
                                 len(list(other.datasets)),
                                 list(self.datasets),
                                 list(other.datasets),
                                 indent=sub_indent))
        else:
            for s, o in zip(self.datasets, other.datasets):
                mismatch += s.find_mismatch(o, indent=sub_indent)
        if len(list(self.fields)) != len(list(other.fields)):
            mismatch += ('\n{indent}mismatching summary field lengths '
                         '(self={} vs other={}): '
                         '\n{indent}  self={}\n{indent}  other={}'
                         .format(len(list(self.fields)),
                                 len(list(other.fields)),
                                 list(self.fields),
                                 list(other.fields),
                                 indent=sub_indent))
        else:
            for s, o in zip(self.fields, other.fields):
                mismatch += s.find_mismatch(o, indent=sub_indent)
        return mismatch

    def __ne__(self, other):
        return not (self == other)

    def __repr__(self):
        return ("Project(num_subjects={}, num_visits={}, "
                "num_datasets={}, num_fields={})".format(
                    len(list(self.subjects)),
                    len(list(self.visits)),
                    len(list(self.datasets)), len(list(self.fields))))


class Subject(object):
    """
    Holds a subject id and a list of sessions
    """

    def __init__(self, subject_id, sessions, datasets, fields):
        self._id = subject_id
        self._sessions = sessions
        self._datasets = datasets
        self._fields = fields
        for session in sessions:
            session.subject = self

    @property
    def id(self):
        return self._id

    def __lt__(self, other):
        return self._id < other._id

    @property
    def sessions(self):
        return iter(self._sessions)

    @property
    def datasets(self):
        return self._datasets

    @property
    def fields(self):
        return self._fields

    @property
    def dataset_names(self):
        return (d.name for d in self.datasets)

    @property
    def field_names(self):
        return (f.name for f in self.fields)

    @property
    def data(self):
        return chain(self.datasets, self.fields)

    @property
    def data_names(self):
        return (d.name for d in self.data)

    def __eq__(self, other):
        if not isinstance(other, Subject):
            return False
        return (self._id == other._id and
                self._sessions == other._sessions and
                self._datasets == other._datasets and
                self._fields == other._fields)

    def find_mismatch(self, other, indent=''):
        if self != other:
            mismatch = "\n{}Subject '{}' != '{}'".format(
                indent, self.id, other.id)
        else:
            mismatch = ''
        sub_indent = indent + '  '
        if self.id != other.id:
            mismatch += ('\n{}id: self={} v other={}'
                         .format(sub_indent, self.id, other.id))
        if len(list(self.sessions)) != len(list(other.sessions)):
            mismatch += ('\n{indent}mismatching session lengths '
                         '(self={} vs other={}): '
                         '\n{indent}  self={}\n{indent}  other={}'
                         .format(len(list(self.sessions)),
                                 len(list(other.sessions)),
                                 list(self.sessions),
                                 list(other.sessions),
                                 indent=sub_indent))
        else:
            for s, o in zip(self.sessions, other.sessions):
                mismatch += s.find_mismatch(o, indent=sub_indent)
        if len(list(self.datasets)) != len(list(other.datasets)):
            mismatch += ('\n{indent}mismatching summary dataset lengths '
                         '(self={} vs other={}): '
                         '\n{indent}  self={}\n{indent}  other={}'
                         .format(len(list(self.datasets)),
                                 len(list(other.datasets)),
                                 list(self.datasets),
                                 list(other.datasets),
                                 indent=sub_indent))
        else:
            for s, o in zip(self.datasets, other.datasets):
                mismatch += s.find_mismatch(o, indent=sub_indent)
        if len(list(self.fields)) != len(list(other.fields)):
            mismatch += ('\n{indent}mismatching summary field lengths '
                         '(self={} vs other={}): '
                         '\n{indent}  self={}\n{indent}  other={}'
                         .format(len(list(self.fields)),
                                 len(list(other.fields)),
                                 list(self.fields),
                                 list(other.fields),
                                 indent=sub_indent))
        else:
            for s, o in zip(self.fields, other.fields):
                mismatch += s.find_mismatch(o, indent=sub_indent)
        return mismatch

    def __ne__(self, other):
        return not (self == other)

    def __repr__(self):
        return ("Subject(id={}, num_sessions={})"
                .format(self._id, len(self._sessions)))


class Visit(object):
    """
    Holds a subject id and a list of sessions
    """

    def __init__(self, visit_id, sessions, datasets, fields):
        self._id = visit_id
        self._sessions = sessions
        self._datasets = datasets
        self._fields = fields
        for session in sessions:
            session.visit = self

    @property
    def id(self):
        return self._id

    def __lt__(self, other):
        return self._id < other._id

    @property
    def sessions(self):
        return iter(self._sessions)

    @property
    def datasets(self):
        return self._datasets

    @property
    def fields(self):
        return self._fields

    @property
    def dataset_names(self):
        return (d.name for d in self.datasets)

    @property
    def field_names(self):
        return (f.name for f in self.fields)

    @property
    def data(self):
        return chain(self.datasets, self.fields)

    @property
    def data_names(self):
        return (d.name for d in self.data)

    def __eq__(self, other):
        if not isinstance(other, Visit):
            return False
        return (self._id == other._id and
                self._sessions == other._sessions and
                self._datasets == other._datasets and
                self._fields == other._fields)

    def find_mismatch(self, other, indent=''):
        if self != other:
            mismatch = "\n{}Visit '{}' != '{}'".format(
                indent, self.id, other.id)
        else:
            mismatch = ''
        sub_indent = indent + '  '
        if self.id != other.id:
            mismatch += ('\n{}id: self={} v other={}'
                         .format(sub_indent, self.id, other.id))
        if len(list(self.sessions)) != len(list(other.sessions)):
            mismatch += ('\n{indent}mismatching session lengths '
                         '(self={} vs other={}): '
                         '\n{indent}  self={}\n{indent}  other={}'
                         .format(len(list(self.sessions)),
                                 len(list(other.sessions)),
                                 list(self.sessions),
                                 list(other.sessions),
                                 indent=sub_indent))
        else:
            for s, o in zip(self.sessions, other.sessions):
                mismatch += s.find_mismatch(o, indent=sub_indent)
        if len(list(self.datasets)) != len(list(other.datasets)):
            mismatch += ('\n{indent}mismatching summary dataset lengths '
                         '(self={} vs other={}): '
                         '\n{indent}  self={}\n{indent}  other={}'
                         .format(len(list(self.datasets)),
                                 len(list(other.datasets)),
                                 list(self.datasets),
                                 list(other.datasets),
                                 indent=sub_indent))
        else:
            for s, o in zip(self.datasets, other.datasets):
                mismatch += s.find_mismatch(o, indent=sub_indent)
        if len(list(self.fields)) != len(list(other.fields)):
            mismatch += ('\n{indent}mismatching summary field lengths '
                         '(self={} vs other={}): '
                         '\n{indent}    self={}\n{indent}    other={}'
                         .format(len(list(self.fields)),
                                 len(list(other.fields)),
                                 list(self.fields),
                                 list(other.fields),
                                 indent=sub_indent))
        else:
            for s, o in zip(self.fields, other.fields):
                mismatch += s.find_mismatch(o, indent=sub_indent)
        return mismatch

    def __ne__(self, other):
        return not (self == other)

    def __repr__(self):
        return "Visit(id={}, num_sessions={})".format(self._id,
                                                      len(self._sessions))


class Session(object):
    """
    Holds the session id and the list of datasets loaded from it

    Parameters
    ----------
    subject_id : str
        The subject ID of the session
    visit_id : str
        The visit ID of the session
    datasets : list(Dataset)
        The datasets found in the session
    processed : Session
        If processed scans are stored in a separate session, it is provided
        here
    """

    def __init__(self, subject_id, visit_id, datasets, fields, processed=None):
        self._subject_id = subject_id
        self._visit_id = visit_id
        self._datasets = datasets
        self._fields = fields
        self._subject = None
        self._visit = None
        self._processed = processed

    @property
    def visit_id(self):
        return self._visit_id

    @property
    def subject_id(self):
        return self._subject_id

    def __lt__(self, other):
        if self.subject_id < other.subject_id:
            return True
        else:
            return self.visit_id < other.visit_id

    @property
    def subject(self):
        return self._subject

    @subject.setter
    def subject(self, subject):
        self._subject = subject

    @property
    def visit(self):
        return self._visit

    @visit.setter
    def visit(self, visit):
        self._visit = visit

    @property
    def processed(self):
        return self._processed

    @processed.setter
    def processed(self, processed):
        self._processed = processed

    @property
    def acquired(self):
        """True if the session contains acquired scans"""
        return not self._processed or self._processed is None

    @property
    def datasets(self):
        return self._datasets

    @property
    def fields(self):
        return self._fields

    @property
    def dataset_names(self):
        return (d.name for d in self.datasets)

    @property
    def field_names(self):
        return (f.name for f in self.fields)

    @property
    def data(self):
        return chain(self.datasets, self.fields)

    @property
    def data_names(self):
        return (d.name for d in self.data)

    @property
    def processed_dataset_names(self):
        datasets = (self.datasets
                    if self.processed is None else self.processed.datasets)
        return (d.name for d in datasets)

    @property
    def processed_field_names(self):
        fields = (self.fields
                  if self.processed is None else self.processed.fields)
        return (f.name for f in fields)

    @property
    def processed_data_names(self):
        return chain(self.processed_dataset_names,
                     self.processed_field_names)

    @property
    def all_dataset_names(self):
        return chain(self.dataset_names, self.processed_dataset_names)

    @property
    def all_field_names(self):
        return chain(self.field_names, self.processed_field_names)

    @property
    def all_data_names(self):
        return chain(self.data_names, self.processed_data_names)

    def __eq__(self, other):
        if not isinstance(other, Session):
            return False
        return (self.subject_id == other.subject_id and
                self.visit_id == other.visit_id and
                self.datasets == other.datasets and
                self.fields == other.fields and
                self.processed == other.processed)

    def find_mismatch(self, other, indent=''):
        if self != other:
            mismatch = "\n{}Session '{}-{}' != '{}-{}'".format(
                indent, self.subject_id, self.visit_id,
                other.subject_id, other.visit_id)
        else:
            mismatch = ''
        sub_indent = indent + '  '
        if self.subject_id != other.subject_id:
            mismatch += ('\n{}subject_id: self={} v other={}'
                         .format(sub_indent, self.subject_id,
                                 other.subject_id))
        if self.visit_id != other.visit_id:
            mismatch += ('\n{}visit_id: self={} v other={}'
                         .format(sub_indent, self.visit_id,
                                 other.visit_id))
        if self.processed != other.processed:
            mismatch += ('\n{}processed: self={} v other={}'
                         .format(sub_indent, self.processed,
                                 other.processed))
        if len(list(self.datasets)) != len(list(other.datasets)):
            mismatch += ('\n{indent}mismatching dataset lengths '
                         '(self={} vs other={}): '
                         '\n{indent}  self={}\n{indent}  other={}'
                         .format(len(list(self.datasets)),
                                 len(list(other.datasets)),
                                 list(self.datasets),
                                 list(other.datasets),
                                 indent=sub_indent))
        else:
            for s, o in zip(self.datasets, other.datasets):
                mismatch += s.find_mismatch(o, indent=sub_indent)
        if len(list(self.fields)) != len(list(other.fields)):
            mismatch += ('\n{indent}mismatching field lengths '
                         '(self={} vs other={}): '
                         '\n{indent}  self={}\n{indent}  other={}'
                         .format(len(list(self.fields)),
                                 len(list(other.fields)),
                                 list(self.fields),
                                 list(other.fields),
                                 indent=sub_indent))
        else:
            for s, o in zip(self.fields, other.fields):
                mismatch += s.find_mismatch(o, indent=sub_indent)
        return mismatch

    def __ne__(self, other):
        return not (self == other)

    def __repr__(self):
        return ("Session(subject_id='{}', visit_id='{}', num_datasets={}, "
                "num_fields={}, processed={})".format(
                    self.subject_id, self.visit_id, len(self._datasets),
                    len(self._fields), self.processed))
