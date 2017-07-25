from abc import ABCMeta, abstractmethod
import os.path
from itertools import chain
from .base import (
    Archive, ArchiveSource, ArchiveSink, ArchiveSourceInputSpec,
    ArchiveSinkInputSpec, ArchiveSubjectSinkInputSpec,
    ArchiveVisitSinkInputSpec,
    ArchiveProjectSinkInputSpec, ArchiveSubjectSink, ArchiveVisitSink,
    ArchiveProjectSink)
import stat
import shutil
import logging
from nipype.interfaces.base import (
    Directory, isdefined)
from .base import Project, Subject, Session
from nianalysis.dataset import Dataset
from nianalysis.exceptions import NiAnalysisError
from nianalysis.data_formats import data_formats
from nianalysis.utils import split_extension
from nianalysis.utils import INPUT_SUFFIX, OUTPUT_SUFFIX


logger = logging.getLogger('NiAnalysis')

SUMMARY_NAME = 'ALL'


class LocalSourceInputSpec(ArchiveSourceInputSpec):

    base_dir = Directory(
        exists=True, desc=("Path to the base directory where the datasets will"
                           " be cached before uploading"))


class LocalSource(ArchiveSource):

    input_spec = LocalSourceInputSpec

    def _list_outputs(self):
        # Directory that holds session-specific
        base_project_dir = os.path.join(self.inputs.base_dir,
                                        str(self.inputs.project_id))
        base_subject_dir = os.path.join(base_project_dir,
                                        str(self.inputs.subject_id))
        session_dir = os.path.join(base_subject_dir,
                                   str(self.inputs.visit_id))
        subject_dir = os.path.join(base_subject_dir, SUMMARY_NAME)
        visit_dir = os.path.join(base_project_dir,
                                     SUMMARY_NAME,
                                     str(self.inputs.visit_id))
        project_dir = os.path.join(base_project_dir, SUMMARY_NAME,
                                   SUMMARY_NAME)
        outputs = {}
        for (name, dataset_format,
             multiplicity, processed) in self.inputs.datasets:
            if multiplicity == 'per_project':
                data_dir = project_dir
            elif multiplicity.startswith('per_subject'):
                data_dir = subject_dir
            elif multiplicity.startswith('per_visit'):
                data_dir = visit_dir
            elif multiplicity.startswith('per_se_ssion'):
                data_dir = session_dir
            else:
                assert False, "Unrecognised multiplicity '{}'".format(
                    multiplicity)
            ext = data_formats[dataset_format].extension
            fname = name + (ext if ext is not None else '')
            # Prepend study name if defined
            if processed and isdefined(self.inputs.study_name):
                fname = self.inputs.study_name + '_' + fname
            outputs[name + OUTPUT_SUFFIX] = os.path.join(data_dir, fname)
        return outputs


class LocalSinkInputSpecMixin(object):

    base_dir = Directory(
        exists=True, desc=("Path to the base directory where the datasets will"
                           " be cached before uploading"))


class LocalSinkInputSpec(ArchiveSinkInputSpec, LocalSinkInputSpecMixin):

    pass


class LocalSubjectSinkInputSpec(ArchiveSubjectSinkInputSpec,
                                LocalSinkInputSpecMixin):
    pass


class LocalVisitSinkInputSpec(ArchiveVisitSinkInputSpec,
                                  LocalSinkInputSpecMixin):
    pass


class LocalProjectSinkInputSpec(ArchiveProjectSinkInputSpec,
                                LocalSinkInputSpecMixin):
    pass


class LocalSinkMixin(object):

    __metaclass = ABCMeta
    input_spec = LocalSinkInputSpec

    def _list_outputs(self):
        """Execute this module.
        """
        # Initiate outputs
        outputs = self._base_outputs()
        out_files = []
        missing_files = []
        # Get output dir from base ArchiveSink class (will change depending on
        # whether it is per session/subject/visit/project)
        out_path = self._get_output_path()
        out_dir = os.path.abspath(os.path.join(*out_path))
        # Make session dir
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, stat.S_IRWXU | stat.S_IRWXG)
        # Loop through datasets connected to the sink and copy them to the
        # cache directory and upload to daris.
        for (name, dataset_format,
             multiplicity, processed) in self.inputs.datasets:
            assert processed, (
                "Should only be sinking processed datasets, not '{}'"
                .format(name))
            filename = getattr(self.inputs, name + INPUT_SUFFIX)
            ext = data_formats[dataset_format].extension
            if not isdefined(filename):
                missing_files.append(name)
                continue  # skip the upload for this file
            assert (split_extension(filename)[1] == ext), (
                "Mismatching extension '{}' for format '{}' ('{}')"
                .format(split_extension(filename)[1],
                        data_formats[dataset_format].name, ext))
            assert multiplicity in self.ACCEPTED_MULTIPLICITIES
            # Copy to local system
            src_path = os.path.abspath(filename)
            out_fname = name + (ext if ext is not None else '')
            if isdefined(self.inputs.study_name):
                out_fname = self.inputs.study_name + '_' + out_fname
            dst_path = os.path.join(out_dir, out_fname)
            out_files.append(dst_path)
            if os.path.isfile(src_path):
                shutil.copyfile(src_path, dst_path)
            elif os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path)
            else:
                assert False
        if missing_files:
            # FIXME: Not sure if this should be an exception or not,
            #        indicates a problem but stopping now would throw
            #        away the datasets that were created
            logger.warning(
                "Missing input datasets '{}' in DarisSink".format(
                    "', '".join(missing_files)))
        # Return cache file paths
        outputs['out_files'] = out_files
        return outputs

    @abstractmethod
    def _get_output_path(self):
        "Get the output path to save the generated datasets into"


class LocalSink(LocalSinkMixin, ArchiveSink):

    input_spec = LocalSinkInputSpec

    def _get_output_path(self):
        return [
            self.inputs.base_dir, self.inputs.project_id,
            self.inputs.subject_id, self.inputs.visit_id]


class LocalSubjectSink(LocalSinkMixin, ArchiveSubjectSink):

    input_spec = LocalSubjectSinkInputSpec

    def _get_output_path(self):
        return [
            self.inputs.base_dir, self.inputs.project_id,
            self.inputs.subject_id, SUMMARY_NAME]


class LocalVisitSink(LocalSinkMixin, ArchiveVisitSink):

    input_spec = LocalVisitSinkInputSpec

    def _get_output_path(self):
        return [
            self.inputs.base_dir, self.inputs.project_id,
            SUMMARY_NAME, self.inputs.visit_id]


class LocalProjectSink(LocalSinkMixin, ArchiveProjectSink):

    input_spec = LocalProjectSinkInputSpec

    def _get_output_path(self):
        return [
            self.inputs.base_dir, self.inputs.project_id, SUMMARY_NAME,
            SUMMARY_NAME]


class LocalArchive(Archive):
    """
    Abstract base class for all Archive systems, DaRIS, XNAT and local file
    system. Sets out the interface that all Archive classes should implement.
    """

    type = 'local'
    Source = LocalSource
    Sink = LocalSink
    SubjectSink = LocalSubjectSink
    VisitSink = LocalVisitSink
    ProjectSink = LocalProjectSink

    def __init__(self, base_dir):
        if not os.path.exists(base_dir):
            raise NiAnalysisError(
                "Base directory for LocalArchive '{}' does not exist"
                .format(base_dir))
        self._base_dir = os.path.abspath(base_dir)

    def __repr__(self):
        return "LocalArchive(base_dir='{}')".format(self.base_dir)

    def source(self, *args, **kwargs):
        source = super(LocalArchive, self).source(*args, **kwargs)
        source.inputs.base_dir = self.base_dir
        return source

    def sink(self, *args, **kwargs):
        sink = super(LocalArchive, self).sink(*args, **kwargs)
        sink.inputs.base_dir = self.base_dir
        return sink

    def project(self, project_id, subject_ids=None, visit_ids=None):
        """
        Return subject and session information for a project in the local
        archive

        Parameters
        ----------
        project_id : str
            ID of the project to inspect
        subject_ids : list(str)
            List of subject IDs with which to filter the tree with. If None all
            are returned
        visit_ids : list(str)
            List of session IDs with which to filter the tree with. If None all
            are returned

        Returns
        -------
        project : nianalysis.archive.Project
            A hierarchical tree of subject, session and dataset information for
            the archive
        """
        project_dir = os.path.join(self.base_dir, str(project_id))
        subjects = []
        subject_dirs = [d for d in os.listdir(project_dir)
                        if not d.startswith('.') and d != SUMMARY_NAME]
        if subject_ids is not None:
            # Ensure ids are strings
            subject_ids = [str(i) for i in subject_ids]
        if subject_ids is not None:
            if any(subject_id not in subject_dirs
                   for subject_id in subject_ids):
                raise NiAnalysisError(
                    "'{}' sujbect(s) is/are missing from '{}' project in local"
                    " archive at '{}' (found '{}')".format(
                        "', '".join(set(subject_ids) - set(subject_dirs)),
                        project_id, self._base_dir, "', '".join(subject_dirs)))
            subject_dirs = subject_ids
        self._check_only_dirs(subject_dirs, project_dir)
        for subject_dir in subject_dirs:
            subject_path = os.path.join(project_dir, subject_dir)
            sessions = []
            session_dirs = [d for d in os.listdir(subject_path)
                            if (not d.startswith('.') and d != SUMMARY_NAME)]
            if visit_ids is not None:
                if any(visit_id not in session_dirs
                       for visit_id in visit_ids):
                    raise NiAnalysisError(
                        "'{}' sessions(s) is/are missing from '{}' subject of "
                        "'{}' project in local archive (found '{}')"
                        .format("', '".join(visit_ids), subject_dir,
                                project_id, "', '".join(session_dirs)))
                session_dirs = visit_ids
            self._check_only_dirs(session_dirs, subject_path)
            # Get datasets in all sessions
            for session_dir in session_dirs:
                session_path = os.path.join(subject_path, session_dir)
                datasets = []
                files = [d for d in os.listdir(session_path)
                            if not os.path.isdir(d)]
                for f in files:
                    datasets.append(
                        Dataset.from_path(os.path.join(session_path, f)))
                sessions.append(Session(session_dir, datasets))
            # Get subject summary datasets
            subject_summary_path = os.path.join(subject_path,
                                                SUMMARY_NAME)
            if os.path.exists(subject_summary_path):
                files = [d for d in os.listdir(subject_summary_path)
                            if not os.path.isdir(d)]
                for f in files:
                    datasets.append(
                        Dataset.from_path(
                            os.path.join(subject_summary_path, f),
                            multiplicity='per_subject'))
            subjects.append(Subject(subject_dir, sessions, datasets))
        # Get project and visit summary datasets
        base_project_summary_path = os.path.join(project_dir, SUMMARY_NAME)
        if os.path.exists(base_project_summary_path):
            project_summary_path = os.path.join(base_project_summary_path,
                                                SUMMARY_NAME)
            if os.path.exists(project_summary_path):
                files = [d for d in os.listdir(project_summary_path)
                         if not os.path.isdir(d)]
                for f in files:
                    datasets.append(
                        Dataset.from_path(
                            os.path.join(project_summary_path, f),
                            multiplicity='per_project'))
            visit_summary_dirs = [d for d in os.listdir(subject_path)
                                   if not (d.startswith('.') and
                                           d == project_summary_path)]
            self._check_only_dirs(visit_summary_dirs,
                                  base_project_summary_path)
            for visit_summary_dir in visit_summary_dirs:
                visit_summary_path = os.path.join(
                    base_project_summary_path, visit_summary_dir)
                files = [d for d in os.listdir(visit_summary_path)
                         if not os.path.isdir(d)]
                for f in files:
                    datasets.append(
                        Dataset.from_path(
                            os.path.join(visit_summary_path, f),
                            multiplicity='per_visit'))
        project = Project(project_id, subjects, datasets)
        return project

    @classmethod
    def _check_only_dirs(cls, dirs, path):
        if any(not os.path.isdir(os.path.join(path, d))
               for d in dirs):
            raise NiAnalysisError(
                "Files found in local archive directory '{}' "
                "('{}') instead of sub-directories".format(
                    path, "', '".join(dirs)))

    def sessions_with_dataset(self, dataset, project_id, sessions=None):
        """
        Return all sessions containing the given dataset

        Parameters
        ----------
        dataset : Dataset
            A file (name) for which to return the sessions that contain it
        project_id : int
            The id of the project
        sessions : List[Session]
            List of sessions of which to test for the dataset
        """
        if sessions is None:
            sessions = self.all_session_ids(project_id)
        with_dataset = []
        for session in sessions:
            if os.path.exists(
                os.path.join(self._base_dir, str(project_id),
                             session.subject_id, session.visit_id,
                             dataset.filename)):
                with_dataset.append(session)
        return with_dataset

    def all_session_ids(self, project_id):
        project = self.project(project_id)
        return chain(*[
            (s.id for s in subj.sessions) for subj in project.subjects])

    @property
    def base_dir(self):
        return self._base_dir
