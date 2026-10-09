"""Registered reference settings shared by the two historical sweep runners."""
from qant_sorting.sorting_schedules import bitonic_sort, rank_sort

ETA_VALUES = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25)
MASTER_SEED = 20260930
MAPPINGS = {
    "Pipelined bitonic adaptation": (bitonic_sort, 1),
    "Rank adaptation": (rank_sort, 2),
}
