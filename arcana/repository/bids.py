from __future__ import absolute_import
import os.path as op
from collections import defaultdict
from itertools import chain
from arcana.utils import makedirs
from .local import LocalRepository
import logging
from bids import grabbids as gb
from .tree import Tree, Subject, Session, Visit
from arcana.dataset import Dataset
from arcana.exception import ArcanaNameError, ArcanaMissingDataException

logger = logging.getLogger('arcana')


class BidsRepository(LocalRepository):
    """
    An 'Repository' class for directories on the local file system organised
    into sub-directories by subject and then visit.

    Parameters
    ----------
    base_dir : str (path)
        Path to local directory containing data
    """

    type = 'bids'
    DERIVATIVES_SUB_PATH = op.join('derivatives')

    def __init__(self, root_dir):
        self._root_dir = root_dir
        derivatives_path = op.join(root_dir,
                                        self.DERIVATIVES_SUB_PATH)
        makedirs(derivatives_path, exist_ok=True)
        LocalRepository.__init__(derivatives_path)
        self._layout = gb.BIDSLayout(self.base_dir)

    @property
    def root_dir(self):
        return self._root_dir

    @property
    def layout(self):
        return self._layout

    def __repr__(self):
        return "BidsRepository(root_dir='{}')".format(self.root_dir)

    def __eq__(self, other):
        try:
            return self.root_dir == other.root_dir
        except AttributeError:
            return False

    def get_dataset(self, dataset):
        """
        Set the path of the dataset from the repository
        """
        raise NotImplementedError

    def tree(self, subject_ids=None, visit_ids=None):
        """
        Return subject and session information for a project in the local
        repository

        Parameters
        ----------
        subject_ids : list(str)
            List of subject IDs with which to filter the tree with. If None all
            are returned
        visit_ids : list(str)
            List of visit IDs with which to filter the tree with. If None all
            are returned

        Returns
        -------
        project : arcana.repository.Tree
            A hierarchical tree of subject, session and dataset information for
            the repository
        """
        bids_datasets = defaultdict(lambda: defaultdict(dict))
        derived_tree = super(BidsRepository, self).tree(
            subject_ids=None, visit_ids=None)
        for bids_obj in self.layout.get(return_type='object'):
            subj_id = bids_obj.entities['subject']
            if subject_ids is not None and subj_id not in subject_ids:
                continue
            visit_id = bids_obj.entities['session']
            if visit_ids is not None and visit_id not in visit_ids:
                continue
            bids_datasets[subj_id][visit_id] = Dataset.from_path(
                bids_obj.path, frequency='per_session',
                subject_id=subj_id, visit_id=visit_id, repository=self,
                bids_attrs=bids_obj)
        # Need to pull out all datasets and fields
        all_sessions = defaultdict(dict)
        all_visit_ids = set()
        for subj_id, visits in bids_datasets.items():
            for visit_id, datasets in visits.items():
                session = Session(
                    subject_id=subj_id, visit_id=visit_id,
                    datasets=datasets)
                try:
                    session.derived = derived_tree.subject(
                        subj_id).visit(visit_id)
                except ArcanaNameError:
                    pass  # No matching derived session
                all_sessions[subj_id][visit_id] = session
                all_visit_ids.add(visit_id)

        subjects = []
        for subj_id, subj_sessions in list(all_sessions.items()):
            try:
                derived_subject = derived_tree.subject(subj_id)
            except ArcanaNameError:
                datasets = []
                fields = []
            else:
                datasets = derived_subject.datasets
                fields = derived_subject.fields
            subjects.append(Subject(
                subj_id, sorted(subj_sessions.values()),
                datasets, fields))
        visits = []
        for visit_id in all_visit_ids:
            try:
                derived_visit = derived_tree.visit(subj_id)
            except ArcanaNameError:
                datasets = []
                fields = []
            else:
                datasets = derived_visit.datasets
                fields = derived_visit.fields
            visit_sessions = list(chain(
                sess[visit_id] for sess in list(all_sessions.values())))
            visits.append(
                Visit(visit_id, sorted(visit_sessions),
                      datasets, fields))
        return Tree(sorted(subjects), sorted(visits),
                       derived_tree.datasets, derived_tree.fields)