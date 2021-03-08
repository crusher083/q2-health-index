# -----------------------------------------------------------------------------
# Copyright (c) 2020-2021, Bioinformatics at Małopolska Centre of Biotechnology
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------

import re
import numpy as np
import pandas as pd

from q2_types.feature_table import (FeatureTable, Frequency, RelativeFrequency)
from q2_health_index._utilities import (_load_and_validate_species,
                                        _load_metadata,
                                        _validate_metadata_is_superset,
                                        _validate_and_extract_healthy_states)


def calculate_gmhi(ctx,
                   table=None,
                   metadata=None,
                   healthy_column=None,
                   healthy_states=None,
                   non_healthy_states=None,
                   healthy_species_fp=None,
                   non_healthy_species_fp=None,
                   rel_thresh=0.00001):

    # Load and validate species lists
    healthy_species_list, non_healthy_species_list = \
        _load_and_validate_species(healthy_species_fp, non_healthy_species_fp)

    # Load and convert feature table (if needed)
    if table.type == FeatureTable[Frequency]:
        get_relative = ctx.get_action('feature_table', 'relative_frequency')
        table, = get_relative(table=table)
    assert table.type == FeatureTable[RelativeFrequency], \
        'Feature table not of the type \'RelativeFrequency\''
    # Keep columns (rows) as samples (species)
    table_df = table.view(pd.DataFrame).T

    # Load metadata
    metadata_df = _load_metadata(metadata)
    # Limit metadata to samples preset in the feature table
    metadata_df = _validate_metadata_is_superset(metadata_df, table_df.T)

    # Validate and extract (non) healthy states
    healthy_states, non_healthy_states = \
        _validate_and_extract_healthy_states(metadata_df,
                                             healthy_column,
                                             healthy_states,
                                             non_healthy_states)

    # Removing unclassified and virus species suitable both for 16S and
    # Metagenome Sequencing if valid taxonomy is provided
    na_species = table_df.index.str.contains('unclassified|virus', regex=True)
    species_profile_2 = table_df[~na_species]

    # Re-normalization of species' relative abundances after removing
    # unclassified and virus species
    species_profile_3 = species_profile_2.apply(lambda x: x / x.sum(), axis=0)
    species_profile_3[species_profile_3 < rel_thresh] = 0

    # Extracting Health-prevalent species
    MH_species = species_profile_3[
        species_profile_3.index.isin(healthy_species_list)]
    # Extracting Health-scarce species
    MN_species = species_profile_3[
        species_profile_3.index.isin(non_healthy_species_list)]

    # Shannon index + Alpha diversity
    MH_not_zero = MH_species[MH_species > 0]
    MN_not_zero = MN_species[MN_species > 0]
    MH_shannon = MH_not_zero.apply(lambda x: -np.sum(np.log(x) * x), axis=0)
    MN_shannon = MN_not_zero.apply(lambda x: -np.sum(np.log(x) * x), axis=0)

    # Richness of Health-prevalent species
    R_MH = MH_not_zero.count()
    # Richness of Health-scarce species
    R_MN = MN_not_zero.count()

    constant = R_MH.rename('h').to_frame().join(R_MN.rename('n').to_frame())

    # Calculating kh and kn
    # kh and kn are 1% of all healthy and non-healthy samples respectively
    if healthy_states != 'rest':
        n_healthy = metadata_df[healthy_column].str.contains(
            '|'.join(healthy_states), flags=re.I, regex=True).sum()
    elif non_healthy_states != 'rest':
        n_non_healthy = metadata_df[healthy_column].str.contains(
            '|'.join(non_healthy_states), flags=re.I, regex=True).sum()
    if healthy_states == 'rest':
        n_healthy = len(metadata_df[healthy_column]) - n_non_healthy
    elif non_healthy_states == 'rest':
        n_non_healthy = len(metadata_df[healthy_column]) - n_healthy
    kh = round(n_healthy / 100)
    kn = round(n_non_healthy / 100)

    # Avoiding zero indices for small groups
    if kh == 0:
        kh += 1
    elif kn == 0:
        kn += 1

    # Median RMH from 1% of the top-ranked samples (see Methods)
    HC1 = constant.sort_values(by=['h', 'n'], ascending=[False, True])
    MH_prime = np.median(HC1[:kh]['h'])

    # Median RMN from 1% of the bottom-ranked samples (see Methods)
    NHC1 = constant.sort_values(by=['h', 'n'], ascending=[True, False])
    MN_prime = np.median(NHC1[:kn]['n'])

    psi_MH = (R_MH / MH_prime) * MH_shannon
    psi_MN = (R_MN / MN_prime) * MN_shannon
    gmhi_df = np.log10((psi_MH + 0.00001) / (psi_MN + 0.00001))
    gmhi_df.name = 'GMHI'

    # Create artifact
    gmhi_artifact = ctx.make_artifact('SampleData[AlphaDiversity]', gmhi_df)

    # Create visualization (box plots) similar to that from alpha-diversity
    get_alpha_diversity_plot = ctx.get_action('diversity',
                                              'alpha_group_significance')
    gmhi_viz = get_alpha_diversity_plot(alpha_diversity=gmhi_artifact,
                                        metadata=metadata)  # returns tuple

    return gmhi_artifact, gmhi_viz[0]
