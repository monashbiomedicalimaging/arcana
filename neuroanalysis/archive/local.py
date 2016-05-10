import os.path
from .base import (
    Archive, ArchiveSource, ArchiveSourceInputSpec, ArchiveSinkInputSpec,
    ArchiveSinkOutputSpec)
import stat
import shutil
import logging
from nipype.pipeline import engine as pe
from nipype.interfaces.io import DataGrabber, DataSink
from nipype.interfaces.base import (
    Directory, isdefined)
from ..base import Session


logger = logging.getLogger('NeuroAnalysis')


class LocalArchive(Archive):
    """
    Abstract base class for all Archive systems, DaRIS, XNAT and local file
    system. Sets out the interface that all Archive classes should implement.
    """

    type = 'Local'

    def __init__(self, base_dir):
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)
        self._base_dir = base_dir

    def source(self, project_id, input_files):
        source = pe.Node(
            DataGrabber(infields=['subject_id', 'study_id'],
                        outfields=[f.name for f in input_files]),
            name="local_source")
        source.inputs.base_directory = os.path.join(self._base_dir,
                                                    str(project_id))
        source.inputs.template = '*'
        field_template = {}
        template_args = {}
        for input_file in input_files:
            field_template[input_file.name] = '%s/%d/{}'.format(
                input_file.filename)
            template_args[input_file.name] = [['subject_id', 'study_id']]
        source.inputs.field_template = field_template
        source.inputs.template_args = template_args
        source.inputs.sort_filelist = False
        return source

    def sink(self, project_id):
        sink = pe.Node(
            DataSink(), name="local_sink")
        sink.inputs.base_directory = os.path.join(self._base_dir,
                                                  str(project_id))
        return sink

    def all_sessions(self, project_id, study_id=None):
        project_dir = os.path.join(self._path, str(project_id))
        sessions = []
        for subject_dir in os.listdir(project_dir):
            study_dirs = os.listdir(os.path.join(project_dir, subject_dir))
            if study_id is not None:
                try:
                    study_ids = [int(study_id)]  # Wrap study_id in list if int
                except TypeError:
                    study_ids = study_id
                study_dirs = [d for d in study_dirs if d in study_ids]
            sessions.extend(Session(int(subject_dir), int(study_dir))
                            for study_dir in study_dirs)
        return sessions

    def sessions_with_file(self, file_, project_id, sessions=None):
        if sessions is None:
            sessions = self.all_sessions(project_id)
        with_dataset = []
        for session in sessions:
            if os.path.exists(os.path.join(
                self._path, str(session.subject_id), str(session.study_id),
                    file_.filename())):
                with_dataset.append(session)
        return with_dataset

    @property
    def base_dir(self):
        return self._base_dir


class LocalSourceInputSpec(ArchiveSourceInputSpec):

    base_dir = Directory(
        exists=True, desc=("Path to the base directory where the files will"
                           " be cached before uploading"))


class LocalSource(ArchiveSource):

    input_spec = LocalSourceInputSpec

    def _list_outputs(self):
        raise NotImplementedError


class LocalSinkInputSpec(ArchiveSinkInputSpec):

    base_dir = Directory(
        exists=True, desc=("Path to the base directory where the files will"
                           " be cached before uploading"))


class LocalSink(DataSink):

    input_spec = LocalSinkInputSpec
    output_spec = ArchiveSinkOutputSpec

    def _list_outputs(self):
        """Execute this module.
        """
        # Initiate outputs
        outputs = self.output_spec().get()
        out_files = []
        missing_files = []
        # Get cache dir for study
        out_dir = os.path.abspath(os.path.join(*(str(d) for d in (
            self.inputs.base_dir, self.inputs.project_id,
            self.inputs.subject_id, self.inputs.name))))
        # Make study cache dir
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, stat.S_IRWXU | stat.S_IRWXG)
        # Loop through files connected to the sink and copy them to the
        # cache directory and upload to daris.
        for name, filename in self.inputs._outputs.iteritems():
            src_path = os.path.abspath(filename)
            if not isdefined(src_path):
                missing_files.append((name, src_path))
                continue  # skip the upload for this file
            # Copy to local cache
            dst_path = os.path.join(out_dir, name)
            out_files.append(dst_path)
            shutil.copyfile(src_path, dst_path)
        if missing_files:
            # FIXME: Not sure if this should be an exception or not,
            #        indicates a problem but stopping now would throw
            #        away the files that were created
            logger.warning(
                "Missing output files '{}' mapped to names '{}' in "
                "DarisSink".format("', '".join(f for _, f in missing_files),
                                   "', '".join(n for n, _ in missing_files)))
        # Return cache file paths
        outputs['out_file'] = out_files
        return outputs
