from typing import Dict

from src.consensus.constants import ConsensusConstants
from src.consensus.pot_iterations import calculate_icp_iters, calculate_ip_iters
from src.types.sized_bytes import bytes32
from src.full_node.sub_block_record import SubBlockRecord
from src.util.ints import uint32, uint64, uint128, uint8
from src.util.significant_bits import (
    count_significant_bits,
    truncate_to_significant_bits,
)


def finishes_sub_epoch(
    constants: ConsensusConstants,
    height: uint32,
    deficit: uint8,
    also_finishes_epoch: bool,
) -> bool:
    """
    Returns true if the next block after header_hash can start a new challenge_slot or not.
    """
    next_height: uint32 = uint32(height + 1)

    # If last slot does not have enough blocks for a new challenge chain infusion, return same difficulty
    if deficit > 0:
        return False

    # If we have not crossed the (sub)epoch barrier in this slot, cannot start new (sub)epoch
    if also_finishes_epoch:
        return height // constants.EPOCH_SUB_BLOCKS != next_height // constants.EPOCH_SUB_BLOCKS

    return height // constants.SUB_EPOCH_SUB_BLOCKS != next_height // constants.SUB_EPOCH_SUB_BLOCKS


def get_next_ips(
    constants: ConsensusConstants,
    height_to_hash: Dict[uint32, bytes32],
    sub_blocks: Dict[bytes32, SubBlockRecord],
    prev_header_hash: bytes32,
    height: uint32,
    deficit: uint8,
    ips: uint64,
    new_slot: bool,
) -> uint64:
    """
    Returns the slot iterations required for the next block after header hash, where new_slot is true iff
    the next block will be in the next slot.
    """
    next_height: uint32 = uint32(height + 1)

    if prev_header_hash not in sub_blocks:
        raise ValueError(f"Header hash {prev_header_hash} not in sub blocks")

    if next_height < constants.EPOCH_SUB_BLOCKS:
        return uint64(constants.IPS_STARTING)

    # If we are in the same epoch, return same ips
    if not new_slot or not finishes_sub_epoch(constants, height, deficit, True):
        return ips

    #       prev epoch surpassed  prev epoch started                  epoch sur.  epoch started
    #        v                       v                                v         v
    #  |.B...B....B. B....B...|......B....B.....B...B.|.B.B.B..|..B...B.B.B...|.B.B.B. B.|........

    height_epoch_surpass: uint32 = next_height % constants.EPOCH_SUB_BLOCKS
    if height_epoch_surpass > constants.MAX_SLOT_SUB_BLOCKS:
        raise ValueError(f"Height at {next_height} should not create a new slot, it is far past the epoch barrier")

    # If the prev slot is the first slot, the iterations start at 0
    # We will compute the timestamps of the last block in epoch, as well as the total iterations at infusion
    first_sb_in_epoch: SubBlockRecord
    prev_slot_start_iters: uint128

    if height_epoch_surpass == 0:
        prev_slot_start_iters = uint128(0)
        # The genesis block is an edge case, where we measure from the first block in epoch, as opposed to the last
        # block in the previous epoch
        if height_to_hash[height - 1] == prev_header_hash:
            prev_slot_time_start = sub_blocks[height_to_hash[uint32(0)]].timestamp
        else:
            pass
    else:
        last_sb_in_prev_epoch: SubBlockRecord = sub_blocks[
            height_to_hash[uint32(height_epoch_surpass - constants.EPOCH_SUB_BLOCKS - 1)]
        ]

        curr: SubBlockRecord = sub_blocks[height_to_hash[last_sb_in_prev_epoch.height + 1]]
        # Wait until the slot finishes with a challenge chain infusion at start of slot
        while not curr.deficit == constants.MIN_SUB_BLOCKS_PER_CHALLENGE_BLOCK - 1:
            last_sb_in_prev_epoch = curr
            curr = sub_blocks[height_to_hash[curr.height + 1]]

        # Ensure that we get a block (which has a timestamp)
        curr = last_sb_in_prev_epoch
        while not curr.is_block:
            curr = sub_blocks[curr.prev_hash]

        prev_slot_start_iters = curr.total_iters
        prev_slot_time_start = curr.timestamp

    # Ensure we get a block for the last block as well
    last_block_curr = sub_block
    while not last_block_curr.is_block:
        last_block_curr = sub_blocks[last_block_curr.prev_hash]

    # This is computed as the iterations per second in last epoch, times the target number of seconds per slot
    new_ips_precise: uint64 = uint64(
        (last_block_curr.total_iters - prev_slot_start_iters) // (last_block_curr.timestamp - prev_slot_time_start)
    )
    new_ips = uint64(truncate_to_significant_bits(new_ips_precise, constants.SIGNIFICANT_BITS))
    assert count_significant_bits(new_ips) <= constants.SIGNIFICANT_BITS

    # Only change by a max factor as a sanity check
    max_ips = uint64(
        truncate_to_significant_bits(
            constants.DIFFICULTY_FACTOR * last_block_curr.ips,
            constants.SIGNIFICANT_BITS,
        )
    )
    min_ips = uint64(
        truncate_to_significant_bits(
            last_block_curr.ips // constants.DIFFICULTY_FACTOR,
            constants.SIGNIFICANT_BITS,
        )
    )
    if new_ips >= last_block_curr.ips:
        return min(new_ips, max_ips)
    else:
        return max([uint64(1), new_ips, min_ips])


def get_next_slot_iters(
    constants: ConsensusConstants,
    height_to_hash: Dict[uint32, bytes32],
    sub_blocks: Dict[bytes32, SubBlockRecord],
    header_hash: bytes32,
    new_slot: bool,
) -> uint64:
    return get_next_ips(constants, height_to_hash, sub_blocks, header_hash, new_slot) * constants.SLOT_TIME_TARGET


def get_difficulty(
    constants: ConsensusConstants,
    sub_blocks: Dict[bytes32, SubBlockRecord],
    header_hash: bytes32,
) -> uint64:
    """
    Returns the difficulty of the sub-block referred to by header_hash
    """
    sub_block = sub_blocks[header_hash]

    if sub_block.height == 0:
        return uint64(constants.DIFFICULTY_STARTING)
    return uint64(sub_block.weight - sub_blocks[sub_block.prev_hash].weight)


def get_next_difficulty(
    constants: ConsensusConstants,
    sub_blocks: Dict[bytes32, SubBlockRecord],
    height_to_hash: Dict[uint32, bytes32],
    prev_header_hash: bytes32,
    height: uint32,
    header_hash: bytes32,
    new_slot: bool,
) -> uint64:
    """
    Returns the difficulty of the next sub-block that extends onto sub-block.
    Used to calculate the number of iterations. When changing this, also change the implementation
    in wallet_state_manager.py.
    """
    next_height: uint32 = uint32(height + 1)

    if prev_header_hash not in sub_blocks:
        raise ValueError(f"Header hash {prev_header_hash} not in sub blocks")

    if next_height < constants.EPOCH_SUB_BLOCKS:
        # We are in the first epoch
        return uint64(constants.DIFFICULTY_STARTING)

    # If we are in the same slot as previous sub-block, return same difficulty
    if not new_slot or not finishes_sub_epoch(constants, sub_block.height, sub_block.deficit, True):
        return get_difficulty(constants, sub_blocks, header_hash)

    height_epoch_surpass: uint32 = next_height % constants.EPOCH_SUB_BLOCKS
    if height_epoch_surpass > constants.MAX_SLOT_SUB_BLOCKS:
        raise ValueError(f"Height at {next_height} should not create a new slot, it is far past the epoch barrier")

    # We will compute the timestamps of the last block in epoch, as well as the total iterations at infusion
    first_sb_in_epoch: SubBlockRecord

    if height_epoch_surpass == 0:
        # The genesis block is a edge case, where we measure from the first block in epoch, as opposed to the last
        # block in the previous epoch
        prev_slot_start_timestamp = sub_blocks[height_to_hash[uint32(0)]].timestamp
        prev_slot_start_weight = 0
    else:
        last_sb_in_prev_epoch: SubBlockRecord = sub_blocks[
            height_to_hash[uint32(height_epoch_surpass - constants.EPOCH_SUB_BLOCKS - 1)]
        ]

        curr: SubBlockRecord = sub_blocks[height_to_hash[last_sb_in_prev_epoch.height + 1]]
        while not curr.deficit == constants.MIN_SUB_BLOCKS_PER_CHALLENGE_BLOCK - 1:
            last_sb_in_prev_epoch = curr
            curr = sub_blocks[height_to_hash[curr.height + 1]]

        last_sb_icp_iters = calculate_icp_iters(
            constants, last_sb_in_prev_epoch.ips, last_sb_in_prev_epoch.required_iters
        )
        last_sb_ip_iters = calculate_ip_iters(
            constants, last_sb_in_prev_epoch.ips, last_sb_in_prev_epoch.required_iters
        )
        last_sb_icp_total_iters = last_sb_in_prev_epoch.total_iters - last_sb_ip_iters + last_sb_icp_iters

        # This fetches the last transaction block before the icp of the last sub-block
        # TODO: check equality
        while curr.total_iters > last_sb_icp_total_iters or not curr.is_block:
            curr = sub_blocks[curr.prev_hash]

        prev_slot_start_timestamp = curr.timestamp
        prev_slot_start_weight = curr.weight

    # Ensure we get a block for the last block as well
    last_block_curr = sub_block
    while not last_block_curr.is_block:
        last_block_curr = sub_blocks[last_block_curr.prev_hash]

    actual_epoch_time = last_block_curr.timestamp - prev_slot_start_timestamp
    old_difficulty = get_difficulty(constants, sub_blocks, last_block_curr)

    # Terms are rearranged so there is only one division.
    new_difficulty_precise = (
        (last_block_curr.weight - prev_slot_start_weight)
        * constants.SLOT_TIME_TARGET
        // (constants.SLOT_SUB_BLOCKS_TARGET * actual_epoch_time)
    )
    # Take only DIFFICULTY_SIGNIFICANT_BITS significant bits
    new_difficulty = uint64(truncate_to_significant_bits(new_difficulty_precise, constants.SIGNIFICANT_BITS))
    assert count_significant_bits(new_difficulty) <= constants.SIGNIFICANT_BITS

    # Only change by a max factor, to prevent attacks, as in greenpaper, and must be at least 1
    max_diff = uint64(
        truncate_to_significant_bits(
            constants.DIFFICULTY_FACTOR * old_difficulty,
            constants.SIGNIFICANT_BITS,
        )
    )
    min_diff = uint64(
        truncate_to_significant_bits(
            old_difficulty // constants.DIFFICULTY_FACTOR,
            constants.SIGNIFICANT_BITS,
        )
    )
    if new_difficulty >= old_difficulty:
        return min(new_difficulty, max_diff)
    else:
        return max([uint64(1), new_difficulty, min_diff])
