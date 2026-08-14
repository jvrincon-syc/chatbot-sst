from __future__ import annotations

from dataclasses import dataclass
import logging
import re

from chunking.application.ports import TokenCounterPort
from chunking.domain.enums import StructuralBlockKind, ZeroOverlapReason
from chunking.domain.models import (
    ChildChunk,
    ChunkingProfile,
    OverlapSpan,
    ParentChunk,
    SourceSpan,
    StructuralBlock,
)
from chunking.infrastructure.canonical_tokenizer import CanonicalTokenizer


logger = logging.getLogger(__name__)
_TABLE_WARNING = "TABLE_CHILD_EXCEEDS_MAX_TOKENS"
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")


@dataclass(frozen=True)
class SentenceUnit:
    """Sentence-like text unit with stable token and character ranges."""

    text: str
    relative_char_start: int
    relative_char_end: int
    char_start: int
    char_end: int
    token_start: int
    token_end: int
    token_count: int


@dataclass(frozen=True)
class ParentSegment:
    """Contiguous subset of one parent text with stable relative offsets."""

    blocks: tuple[StructuralBlock, ...]
    relative_char_start: int
    relative_char_end: int


class ChildChunkBuilder:
    """Builds retrieval children with bounded semantic overlap."""

    def __init__(self, tokenizer: TokenCounterPort | None = None) -> None:
        self._tokenizer = tokenizer or CanonicalTokenizer()

    def build(
        self,
        *,
        parent: ParentChunk,
        blocks: tuple[StructuralBlock, ...],
        profile: ChunkingProfile,
    ) -> tuple[ChildChunk, ...]:
        if self._is_mixed_parent(blocks):
            return self._build_mixed_children(parent=parent, profile=profile, blocks=blocks)
        if self._is_table_parent(blocks):
            return self._build_table_children(parent=parent, profile=profile, blocks=blocks)
        if self._is_atomic_parent(parent=parent, blocks=blocks, profile=profile):
            return (self._build_atomic_child(parent=parent, profile=profile, blocks=blocks),)
        return self._build_continuous_children(parent=parent, profile=profile)

    def _build_mixed_children(
        self,
        *,
        parent: ParentChunk,
        profile: ChunkingProfile,
        blocks: tuple[StructuralBlock, ...],
    ) -> tuple[ChildChunk, ...]:
        children: list[ChildChunk] = []
        next_ordinal = 0
        for segment_index, segment in enumerate(self._segment_parent_blocks(parent=parent, blocks=blocks)):
            segment_text = parent.text[segment.relative_char_start : segment.relative_char_end].strip()
            if not segment_text:
                continue
            segment_parent = ParentChunk.create(
                document_id=parent.document_id,
                profile_id=parent.profile_id,
                ordinal=segment_index,
                text=segment_text,
                source_span=self._merge_source_spans(segment.blocks),
                block_ids=tuple(block.block_id for block in segment.blocks),
                # Inherit the section so the recursive build folds it into each
                # child's context prefix exactly once (never double-applied here).
                section_title=parent.section_title,
                section_path=parent.section_path,
            )
            segment_children = self.build(
                parent=segment_parent,
                blocks=segment.blocks,
                profile=profile,
            )
            token_prefix = self._tokenizer.count_tokens(parent.text[: segment.relative_char_start])
            for child in segment_children:
                children.append(
                    ChildChunk.create(
                        document_id=child.document_id,
                        profile_id=child.profile_id,
                        parent_id=parent.chunk_id,
                        ordinal=next_ordinal,
                        text=child.text,
                        source_span=child.source_span,
                        token_start=token_prefix + child.token_start,
                        token_end=token_prefix + child.token_end,
                        token_count=child.token_count,
                        overlap_previous_tokens=child.overlap_previous_tokens,
                        overlap_next_tokens=child.overlap_next_tokens,
                        overlap_previous_span=child.overlap_previous_span,
                        overlap_next_span=child.overlap_next_span,
                        context_prefix=child.context_prefix,
                        zero_overlap_reasons=child.zero_overlap_reasons,
                        warnings=child.warnings,
                        section_title=child.section_title,
                        section_path=child.section_path,
                    )
                )
                next_ordinal += 1
        return tuple(children)

    def _build_table_children(
        self,
        *,
        parent: ParentChunk,
        profile: ChunkingProfile,
        blocks: tuple[StructuralBlock, ...],
    ) -> tuple[ChildChunk, ...]:
        table_block = next(
            block for block in blocks if block.kind is StructuralBlockKind.TABLE
        )
        lines = [line for line in table_block.text.splitlines() if line.strip()]
        header_lines = tuple(lines[:2]) if len(lines) >= 2 and lines[0].strip().startswith("|") else tuple(lines[:1])
        data_lines = lines[2:] if len(header_lines) == 2 else lines[1:]
        header_text = "\n".join(header_lines)
        header_tokens = self._tokenizer.count_tokens(header_text) if header_text else 0
        groups: list[list[str]] = []
        current: list[str] = []
        current_tokens = 0
        for line in data_lines:
            line_tokens = self._tokenizer.count_tokens(line)
            projected = current_tokens + line_tokens + header_tokens
            if current and projected > profile.child_max_tokens:
                groups.append(current)
                current = [line]
                current_tokens = line_tokens
                continue
            current.append(line)
            current_tokens += line_tokens
        if current:
            groups.append(current)
        if not groups:
            groups = [data_lines or list(lines)]

        children: list[ChildChunk] = []
        char_cursor = table_block.source_span.char_start
        token_cursor = 0
        for ordinal, group in enumerate(groups):
            text = "\n".join(group)
            base_prefix = "" if ordinal == 0 else header_text
            context_prefix = self._section_prefix(
                parent=parent,
                profile=profile,
                base_prefix=base_prefix,
            )
            full_text = self._full_text(context_prefix=context_prefix, text=text)
            token_count = self._tokenizer.count_tokens(full_text)
            warnings = ()
            if token_count > profile.child_max_tokens:
                warnings = (_TABLE_WARNING,)
            char_end = char_cursor + len(text)
            zero_overlap_reasons = frozenset(
                {
                    ZeroOverlapReason.DOCUMENT_START,
                    ZeroOverlapReason.SECTION_BOUNDARY,
                    ZeroOverlapReason.TABLE_OR_FORM_BOUNDARY,
                }
            )
            children.append(
                ChildChunk.create(
                    document_id=parent.document_id,
                    profile_id=profile.profile_id,
                    parent_id=parent.chunk_id,
                    ordinal=ordinal,
                    text=text,
                    source_span=SourceSpan(
                        page_start=table_block.source_span.page_start,
                        page_end=table_block.source_span.page_end,
                        char_start=char_cursor,
                        char_end=char_end,
                    ),
                    token_start=token_cursor,
                    token_end=token_cursor + self._tokenizer.count_tokens(text),
                    token_count=token_count,
                    overlap_previous_tokens=0,
                    overlap_next_tokens=0,
                    context_prefix=context_prefix,
                    zero_overlap_reasons=zero_overlap_reasons,
                    warnings=warnings,
                    section_title=parent.section_title,
                    section_path=parent.section_path,
                )
            )
            char_cursor = char_end + 1
            token_cursor += self._tokenizer.count_tokens(text)
        return tuple(children)

    def _build_atomic_child(
        self,
        *,
        parent: ParentChunk,
        profile: ChunkingProfile,
        blocks: tuple[StructuralBlock, ...],
    ) -> ChildChunk:
        reasons = {ZeroOverlapReason.DOCUMENT_START, ZeroOverlapReason.SECTION_BOUNDARY}
        if any(block.kind in {StructuralBlockKind.TABLE, StructuralBlockKind.FORM} for block in blocks):
            reasons.add(ZeroOverlapReason.TABLE_OR_FORM_BOUNDARY)
        return ChildChunk.create(
            document_id=parent.document_id,
            profile_id=profile.profile_id,
            parent_id=parent.chunk_id,
            ordinal=0,
            text=parent.text,
            source_span=parent.source_span,
            token_start=0,
            token_end=self._tokenizer.count_tokens(parent.text),
            token_count=self._tokenizer.count_tokens(parent.text),
            overlap_previous_tokens=0,
            overlap_next_tokens=0,
            context_prefix=self._section_prefix(parent=parent, profile=profile),
            zero_overlap_reasons=frozenset(reasons),
            section_title=parent.section_title,
            section_path=parent.section_path,
        )

    def _build_continuous_children(
        self,
        *,
        parent: ParentChunk,
        profile: ChunkingProfile,
    ) -> tuple[ChildChunk, ...]:
        units = self._sentence_units(parent)
        unique_chunks = self._partition_units(units=units, profile=profile)
        overlap_target = profile.overlap_tokens_for_target()
        overlap_units_by_pair: list[tuple[SentenceUnit, ...]] = []
        for index in range(len(unique_chunks) - 1):
            overlap_units_by_pair.append(
                self._select_overlap_units(
                    parent_text=parent.text,
                    units=unique_chunks[index],
                    nominal_target=overlap_target,
                    profile=profile,
                )
            )

        children: list[ChildChunk] = []
        for ordinal, unique_units in enumerate(unique_chunks):
            previous_overlap_units = overlap_units_by_pair[ordinal - 1] if ordinal > 0 else ()
            next_overlap_units = overlap_units_by_pair[ordinal] if ordinal < len(overlap_units_by_pair) else ()
            emitted_units = (*previous_overlap_units, *unique_units)
            child_relative_start = emitted_units[0].relative_char_start
            child_relative_end = emitted_units[-1].relative_char_end
            text = parent.text[child_relative_start:child_relative_end].strip()
            token_start = self._tokenizer.count_tokens(parent.text[:child_relative_start])
            token_end = self._tokenizer.count_tokens(parent.text[:child_relative_end])
            token_count = self._tokenizer.count_tokens(text)
            previous_overlap_tokens = self._overlap_token_count(
                parent_text=parent.text,
                units=previous_overlap_units,
            )
            next_overlap_tokens = self._overlap_token_count(
                parent_text=parent.text,
                units=next_overlap_units,
            )
            zero_overlap_reasons = set()
            if previous_overlap_tokens == 0:
                zero_overlap_reasons.add(ZeroOverlapReason.DOCUMENT_START)
            if next_overlap_tokens == 0:
                zero_overlap_reasons.add(ZeroOverlapReason.SECTION_BOUNDARY)
            children.append(
                ChildChunk.create(
                    document_id=parent.document_id,
                    profile_id=profile.profile_id,
                    parent_id=parent.chunk_id,
                    ordinal=ordinal,
                    text=text,
                    source_span=SourceSpan(
                        page_start=parent.source_span.page_start,
                        page_end=parent.source_span.page_end,
                        char_start=min(unit.char_start for unit in emitted_units),
                        char_end=max(unit.char_end for unit in emitted_units),
                    ),
                    token_start=token_start,
                    token_end=token_end,
                    token_count=token_count,
                    overlap_previous_tokens=previous_overlap_tokens,
                    overlap_next_tokens=next_overlap_tokens,
                    overlap_previous_span=(
                        OverlapSpan(token_start=0, token_end=previous_overlap_tokens)
                        if previous_overlap_tokens > 0
                        else None
                    ),
                    overlap_next_span=(
                        OverlapSpan(
                            token_start=token_count - next_overlap_tokens,
                            token_end=token_count,
                        )
                        if next_overlap_tokens > 0
                        else None
                    ),
                    context_prefix=self._section_prefix(parent=parent, profile=profile),
                    zero_overlap_reasons=frozenset(zero_overlap_reasons),
                    section_title=parent.section_title,
                    section_path=parent.section_path,
                )
            )
        logger.info(
            "Built child chunks",
            extra={
                "document_id": parent.document_id,
                "parent_id": parent.chunk_id,
                "child_count": len(children),
            },
        )
        return tuple(children)

    def _overlap_token_count(
        self,
        *,
        parent_text: str,
        units: tuple[SentenceUnit, ...],
    ) -> int:
        if not units:
            return 0
        start = units[0].relative_char_start
        end = units[-1].relative_char_end
        return self._tokenizer.count_tokens(parent_text[start:end].strip())

    def _partition_units(
        self,
        *,
        units: tuple[SentenceUnit, ...],
        profile: ChunkingProfile,
    ) -> tuple[tuple[SentenceUnit, ...], ...]:
        unique_target = profile.child_target_tokens - profile.overlap_tokens_for_target()
        unique_minimum = max(1, profile.child_min_tokens - profile.overlap_max_tokens)
        unique_maximum = profile.child_max_tokens - profile.overlap_max_tokens
        chunks: list[list[SentenceUnit]] = []
        current: list[SentenceUnit] = []
        current_tokens = 0
        for unit in units:
            projected = current_tokens + unit.token_count
            should_close = (
                current
                and current_tokens >= unique_minimum
                and (current_tokens >= unique_target or projected > unique_maximum)
            )
            if should_close:
                chunks.append(current)
                current = [unit]
                current_tokens = unit.token_count
                continue
            current.append(unit)
            current_tokens = projected
        if current:
            chunks.append(current)
        if len(chunks) > 1:
            last_tokens = sum(unit.token_count for unit in chunks[-1])
            penultimate_tokens = sum(unit.token_count for unit in chunks[-2])
            if (
                last_tokens < unique_minimum
                and penultimate_tokens + last_tokens <= unique_maximum
            ):
                chunks[-2].extend(chunks[-1])
                chunks.pop()
        return tuple(tuple(chunk) for chunk in chunks)

    def _select_overlap_units(
        self,
        *,
        parent_text: str,
        units: tuple[SentenceUnit, ...],
        nominal_target: int,
        profile: ChunkingProfile,
    ) -> tuple[SentenceUnit, ...]:
        selected: list[SentenceUnit] = []
        best: tuple[SentenceUnit, ...] = ()
        best_distance = profile.child_max_tokens
        for unit in reversed(units):
            selected.insert(0, unit)
            token_total = self._overlap_token_count(
                parent_text=parent_text,
                units=tuple(selected),
            )
            if token_total > profile.overlap_max_tokens:
                selected.pop(0)
                break
            if profile.overlap_min_tokens <= token_total <= profile.overlap_max_tokens:
                distance = abs(token_total - nominal_target)
                if distance < best_distance:
                    best = tuple(selected)
                    best_distance = distance
        return best

    def _sentence_units(self, parent: ParentChunk) -> tuple[SentenceUnit, ...]:
        parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(parent.text) if part.strip()]
        units: list[SentenceUnit] = []
        search_start = 0
        for part in parts:
            location = parent.text.find(part, search_start)
            if location < 0:
                location = search_start
            relative_char_start = location
            relative_char_end = relative_char_start + len(part)
            char_start = parent.source_span.char_start + relative_char_start
            char_end = parent.source_span.char_start + relative_char_end
            units.append(
                SentenceUnit(
                    text=part,
                    relative_char_start=relative_char_start,
                    relative_char_end=relative_char_end,
                    char_start=char_start,
                    char_end=char_end,
                    token_start=self._tokenizer.count_tokens(parent.text[:relative_char_start]),
                    token_end=self._tokenizer.count_tokens(parent.text[:relative_char_end]),
                    token_count=self._tokenizer.count_tokens(part),
                )
            )
            search_start = relative_char_end
        return tuple(units)

    def _is_atomic_parent(
        self,
        *,
        parent: ParentChunk,
        blocks: tuple[StructuralBlock, ...],
        profile: ChunkingProfile,
    ) -> bool:
        token_count = self._tokenizer.count_tokens(parent.text)
        if token_count <= profile.child_max_tokens:
            return True
        return len(blocks) == 1 and blocks[0].kind is StructuralBlockKind.FORM

    def _is_table_parent(self, blocks: tuple[StructuralBlock, ...]) -> bool:
        return any(block.kind is StructuralBlockKind.TABLE for block in blocks)

    def _is_mixed_parent(self, blocks: tuple[StructuralBlock, ...]) -> bool:
        non_heading = [
            block
            for block in blocks
            if block.kind is not StructuralBlockKind.HEADING
        ]
        has_tabular = any(
            block.kind in {StructuralBlockKind.TABLE, StructuralBlockKind.FORM}
            for block in non_heading
        )
        has_narrative = any(
            block.kind not in {StructuralBlockKind.TABLE, StructuralBlockKind.FORM}
            for block in non_heading
        )
        return has_tabular and has_narrative

    def _segment_parent_blocks(
        self,
        *,
        parent: ParentChunk,
        blocks: tuple[StructuralBlock, ...],
    ) -> tuple[ParentSegment, ...]:
        segments: list[ParentSegment] = []
        current_blocks: list[StructuralBlock] = []
        current_start: int | None = None
        current_end: int | None = None
        cursor = 0
        for index, block in enumerate(blocks):
            block_start = cursor
            block_end = block_start + len(block.text)
            is_tabular = block.kind in {StructuralBlockKind.TABLE, StructuralBlockKind.FORM}
            if is_tabular:
                if current_blocks and current_start is not None and current_end is not None:
                    segments.append(
                        ParentSegment(
                            blocks=tuple(current_blocks),
                            relative_char_start=current_start,
                            relative_char_end=current_end,
                        )
                    )
                    current_blocks = []
                    current_start = None
                    current_end = None
                segments.append(
                    ParentSegment(
                        blocks=(block,),
                        relative_char_start=block_start,
                        relative_char_end=block_end,
                    )
                )
            else:
                if current_start is None:
                    current_start = block_start
                current_blocks.append(block)
                current_end = block_end
            cursor = block_end
            if index < len(blocks) - 1:
                cursor += 2
        if current_blocks and current_start is not None and current_end is not None:
            segments.append(
                ParentSegment(
                    blocks=tuple(current_blocks),
                    relative_char_start=current_start,
                    relative_char_end=current_end,
                )
            )
        return tuple(segments)

    def _merge_source_spans(self, blocks: tuple[StructuralBlock, ...]) -> SourceSpan:
        spans = tuple(block.source_span for block in blocks)
        page_numbers = [
            span.page_start
            for span in spans
            if span.page_start is not None and span.page_end is not None
        ]
        page_ends = [
            span.page_end
            for span in spans
            if span.page_start is not None and span.page_end is not None
        ]
        if len(page_numbers) != len(spans):
            page_start = None
            page_end = None
        else:
            page_start = min(page_numbers)
            page_end = max(page_ends)
        return SourceSpan(
            page_start=page_start,
            page_end=page_end,
            char_start=min(span.char_start for span in spans),
            char_end=max(span.char_end for span in spans),
        )

    def _full_text(self, *, context_prefix: str, text: str) -> str:
        if not context_prefix:
            return text
        return f"{context_prefix}\n{text}"

    def _section_prefix(
        self,
        *,
        parent: ParentChunk,
        profile: ChunkingProfile,
        base_prefix: str = "",
    ) -> str:
        """Fold the section heading into a child's context prefix (opt-in).

        Only profiles with ``include_section_context`` and a parent carrying a
        ``section_title`` change anything; otherwise the base prefix is returned
        untouched so v1 children stay byte-identical. The heading is prepended so
        the embedded string leads with the section context.
        """
        if not profile.include_section_context or not parent.section_title:
            return base_prefix
        if not base_prefix:
            return parent.section_title
        return f"{parent.section_title}\n{base_prefix}"
