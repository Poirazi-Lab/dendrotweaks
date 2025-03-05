from dendrotweaks.morphology.trees import Node, Tree
from dendrotweaks.morphology.point_trees import Point, PointTree
from dendrotweaks.morphology.sec_trees import Section, SectionTree
from dendrotweaks.morphology.seg_trees import Segment, SegmentTree

from dendrotweaks.morphology.io.reader import SWCReader

from typing import List, Union
import numpy as np
from pandas import DataFrame

from dendrotweaks.morphology.io.validation import validate_tree



def create_point_tree(source: Union[str, DataFrame]) -> PointTree:
    """
    Creates a point tree from either a file path or a DataFrame.
    
    Parameters:
        source (str | pd.DataFrame): File path to the SWC file or a preprocessed DataFrame.
    """
    if isinstance(source, str):
        reader = SWCReader()
        df = reader.read_file(source)
    elif isinstance(source, DataFrame):
        df = source
    else:
        raise ValueError("Source must be a file path (str) or a DataFrame.")

    nodes = [
        Point(row['Index'], row['Type'], row['X'], row['Y'], row['Z'], row['R'], row['Parent'])
        for _, row in df.iterrows()
    ]
    point_tree =  PointTree(nodes)
    point_tree.remove_overlaps()

    return point_tree


def create_section_tree(point_tree: PointTree):
    """
    Creates a section tree from an SWC tree.

    Parameters
    ----------
    point_tree : PointTree
        The SWC tree to be partitioned into a section tree.
    Returns
    -------
    SectionTree
        The section tree created from the SWC tree.
    """

    point_tree.extend_sections()
    point_tree.sort()

    sections = _split_to_sections(point_tree)

    sec_tree = SectionTree(sections)
    sec_tree._point_tree = point_tree

    return sec_tree


def _split_to_sections(point_tree: PointTree) -> List[Section]:

    sections = []

    bifurcation_children = [
        child for b in point_tree.bifurcations for child in b.children]
    bifurcation_children = [point_tree.root] + bifurcation_children
    # bifurcation_children = sorted(bifurcation_children,
    #                               key=lambda x: x.idx)
    # Filter out the bifurcation children to enforce the original order
    bifurcation_children = [node for node in point_tree._nodes 
                            if node in bifurcation_children]

    # Assign a section to each bifurcation child
    for i, child in enumerate(bifurcation_children):
        section = Section(idx=i, parent_idx=-1, points=[child])
        sections.append(section)
        child._section = section
        # Propagate the section to the children until the next 
        # bifurcation or termination point is reached
        while child.children:
            next_child = child.children[0]
            if next_child in bifurcation_children:
                break
            next_child._section = section
            section.points.append(next_child)
            child = next_child

        section.parent = section.points[0].parent._section if section.points[0].parent else None
        section.parent_idx = section.parent.idx if section.parent else -1


    if point_tree.soma_notation == '3PS':
        sections = _merge_soma(sections, point_tree)

    return sections


def _merge_soma(sections: List[Section], point_tree: PointTree):
    """
    If soma has 3PS notation, merge it into one section.
    """

    true_soma = point_tree.root._section
    true_soma.idx = 0
    true_soma.parent_idx = -1

    false_somas = [sec for sec in sections 
        if sec.domain == 'soma' and sec is not true_soma]
    if len(false_somas) != 2:
        print(false_somas)
        raise ValueError('Soma must have exactly 2 children of domain soma.')

    for i, sec in enumerate(false_somas):
        sections.remove(sec)
        if len(sec.points) != 1:
            raise ValueError('Soma children must have exactly 1 point.')
        for pt in sec.points:
            pt._section = true_soma

    true_soma.points = [
        false_somas[0].points[0], 
        true_soma.points[0], 
        false_somas[1].points[0]
    ]

    for sec in sections:
        if sec is true_soma:
            continue
        sec.idx -= 2
        sec.parent_idx = sec.points[0].parent._section.idx
        

    return sections


def create_segment_tree(sec_tree):

    segments = _create_segments(sec_tree)

    seg_tree = SegmentTree(segments)
    sec_tree._seg_tree = seg_tree

    return seg_tree


def _create_segments(sec_tree) -> List[Segment]:

    """
    Build the segment tree using the section tree.
    """

    segments = []  # To store Segment objects
    # TODO: Refactor this to use a stack instead of recursion
    def add_segments(sec, parent_idx, idx_counter):
        segs = {seg: idx + idx_counter for idx, seg in enumerate(sec._ref)}

        sec.segments = []
        # Add each segment of this section as a Segment object
        for seg, idx in segs.items():
            # Create a Segment object with the parent index
            segment = Segment(
                idx=idx, parent_idx=parent_idx, neuron_seg=seg, section=sec)
            segments.append(segment)
            sec.segments.append(segment)

            # Update the parent index for the next segment in this section
            parent_idx = idx

        # Update idx_counter for the next section
        idx_counter += len(segs)

        # Recursively add child sections
        for child in sec.children:
            # IMPORTANT: This is needed since 0 and 1 segments are not explicitly
            # defined in the section segments list
            if child._ref.parentseg().x == 1:
                new_parent_idx = list(segs.values())[-1]
            elif child._ref.parentseg().x == 0:
                new_parent_idx = list(segs.values())[0]
            else:
                new_parent_idx = segs[child._ref.parentseg()]
            # Recurse for the child section
            idx_counter = add_segments(child, new_parent_idx, idx_counter)

        return idx_counter

    # Start with the root section of the sec_tree
    add_segments(sec_tree.root, parent_idx=-1, idx_counter=0)

    return segments
        