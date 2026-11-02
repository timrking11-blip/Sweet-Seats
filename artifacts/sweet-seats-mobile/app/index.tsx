import { useCallback, useState } from 'react';
import { FlatList, Platform, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { KeyboardAvoidingView } from 'react-native-keyboard-controller';
import { Feather } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useGetDiscoveryEvents, getGetDiscoveryEventsQueryKey, type DiscoveryEvent } from '@workspace/api-client-react';
import { useColors } from '@/hooks/useColors';
import { Button, Copy, Eyebrow, Heading, Notice, RemoteState, eventTime, feedWarnings, fonts, matchesSearch, observedTime, usePageInsets } from '@/components/discovery-ui';

function EventCard({ event, index }: { event: DiscoveryEvent; index: number }) {
  const c = useColors();
  const accent = [c.accent, c.coral, c.primary][index % 3];
  const month = new Date(`${event.local_date}T12:00:00Z`).toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' });
  return <Pressable accessibilityRole="button" accessibilityLabel={`Explore ${event.title}`} testID={`event-${event.event_id}`}
    onPress={() => { if (Platform.OS !== 'web') void Haptics.selectionAsync().catch(() => {}); router.push({ pathname: '/events/[id]', params: { id: event.event_id } }); }}
    style={({ pressed }) => [styles.card, { backgroundColor: c.card, borderColor: c.border, opacity: pressed ? 0.72 : 1 }]}>
    <View pointerEvents="none" style={[styles.glow, { backgroundColor: accent }]} />
    <View style={styles.row}><Eyebrow>{event.status.toUpperCase()}</Eyebrow><Text style={{ color: event.stale ? c.primary : c.success, fontSize: 10 }}>{event.stale ? 'Stale observation' : 'Recent observation'}</Text></View>
    <View style={[styles.row, { alignItems: 'flex-start', gap: 16, marginVertical: 20 }]}>
      <View style={[styles.date, { borderColor: c.border }]}><Text style={{ color: c.mutedForeground, fontSize: 10 }}>{month.toUpperCase()}</Text><Text style={[styles.day, { color: accent }]}>{event.local_date.slice(-2)}</Text></View>
      <View style={{ flex: 1, gap: 3 }}><Text style={[styles.eventTitle, { color: c.foreground }]}>{event.title}</Text><Copy>{event.performers.map(p => p.name).join(' · ') || 'Lineup not provided'}</Copy><Copy>{event.venue.name}</Copy><Copy muted>{event.venue.neighborhood} · {eventTime(event)}</Copy></View>
    </View>
    <Copy muted>{event.sources.length} synthetic source {event.sources.length === 1 ? 'record' : 'records'}</Copy>
    <Copy muted>Observed {observedTime(event.observed_at)}</Copy>
    <View style={[styles.row, { marginTop: 16 }]}><Text style={{ color: c.primary, fontSize: 14, fontWeight: '700' }}>Explore this night</Text><Feather name="arrow-up-right" size={20} color={c.primary} /></View>
  </Pressable>;
}

export default function DiscoveryScreen() {
  const c = useColors();
  const insets = usePageInsets();
  const [query, setQuery] = useState<string>('');
  const [offset, setOffset] = useState<number>(0);
  const [showSources, setShowSources] = useState<boolean>(false);
  const params = { limit: 100, offset };
  const feed = useGetDiscoveryEvents(params, { query: { queryKey: getGetDiscoveryEventsQueryKey(params) }, request: { cache: 'no-store', timeoutMs: 8000 } });
  useFocusEffect(useCallback(() => { void feed.refetch(); }, [feed.refetch]));
  const data = !feed.isError && !feed.isFetching && feed.data?.mode === 'synthetic' ? feed.data : undefined;
  const matches = data?.events.filter(event => matchesSearch(event, query)) ?? [];
  const page = (next: number) => { setQuery(''); setOffset(next); };
  return <KeyboardAvoidingView behavior="padding" style={{ flex: 1, backgroundColor: c.background }}>
    <FlatList data={matches} keyExtractor={event => event.event_id} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag"
      contentContainerStyle={[styles.page, insets]}
      refreshControl={<RefreshControl refreshing={feed.isFetching} onRefresh={() => void feed.refetch()} tintColor={c.primary} />}
      ListHeaderComponent={<View style={styles.header}>
        <View style={[styles.row, styles.topbar, { borderColor: c.border }]}><Text style={[styles.brand, { color: c.foreground }]}>sweet seats</Text><Eyebrow>LOCAL DEMO</Eyebrow></View>
        <Eyebrow>NEW YORK · LIVE MUSIC</Eyebrow>
        <Text accessibilityRole="header" style={[styles.hero, { color: c.foreground }]}>Catch the nights{'\n'}you'd hate to miss.</Text>
        <Copy muted>Small rooms. Big nights. A clear trail back to where every detail came from.</Copy>
        <Notice>Invented events, artists, and venues. No live sources or notifications are active.</Notice>
        <View style={[styles.row, { marginTop: 12 }]}><Heading>A few nights{'\n'}to explore</Heading><Pressable accessibilityRole="button" accessibilityLabel="Refresh feed" testID="refresh-feed" disabled={feed.isFetching} onPress={() => void feed.refetch()} style={{ padding: 12, opacity: feed.isFetching ? 0.4 : 1 }}><Feather name="refresh-cw" size={22} color={c.primary} /></Pressable></View>
        <Copy muted>Find an artist, venue, or neighborhood on this page</Copy>
        <View style={[styles.search, { borderColor: c.input, backgroundColor: c.secondary }]}><Feather name="search" size={19} color={c.mutedForeground} /><TextInput testID="event-search" accessibilityLabel="Search events on this page" placeholder="Try Violet Static or Brooklyn" placeholderTextColor={c.mutedForeground} value={query} onChangeText={setQuery} autoCorrect={false} returnKeyType="search" style={[styles.input, { color: c.foreground }]} /></View>
        {feed.isFetching ? <RemoteState loading /> : !data ? <RemoteState retry={() => void feed.refetch()} /> : <>
          {feedWarnings(data).map(message => <Notice key={message}>{message}</Notice>)}
          {data.unresolved.map(record => <Notice key={record.source_record_id}>{record.title}: identity crosswalk needs review; no match was guessed. {record.reason}</Notice>)}
          <Copy muted>{matches.length} demo {matches.length === 1 ? 'night' : 'nights'} · NYC area</Copy>
          {matches.length === 0 && !['unavailable', 'blocked', 'review_required'].includes(data.status) && <View style={{ gap: 12, paddingVertical: 20 }}><Heading>{query.trim() ? 'Nothing matches this search.' : 'No events returned.'}</Heading><Copy muted>{query.trim() ? 'Try another artist, venue, or neighborhood.' : 'Collection succeeded without events. That does not mean tickets are sold out.'}</Copy></View>}
        </>}
      </View>}
      renderItem={({ item, index }) => <EventCard event={item} index={index} />}
      ListFooterComponent={<View style={{ gap: 22, marginTop: 24 }}>
        {data && <>
          <View style={styles.row}><Button label="Previous" testID="previous-page" disabled={offset === 0} onPress={() => page(Math.max(0, offset - 100))} /><Button label="Next" testID="next-page" disabled={data.pagination.next_offset === null} onPress={() => page(data.pagination.next_offset ?? 0)} /></View>
          <Copy muted>{data.pagination.total} total demo events · Page {Math.floor(offset / 100) + 1}</Copy>
          <Button label={showSources ? 'Hide collection results' : 'Source collection results'} testID="collection-results" onPress={() => setShowSources(value => !value)} />
          {showSources && data.collections.map((source, i) => <View key={i} style={{ gap: 4 }}><Copy>{source.name}: {source.status}</Copy><Copy muted>{source.item_count} records · {observedTime(source.finished_at)}</Copy></View>)}
        </>}
        <View style={[styles.about, { borderColor: c.border }]}><Eyebrow>BUILT ON RECEIPTS</Eyebrow><Heading>Every detail{'\n'}has a source.</Heading><Copy muted>This local preview follows synthetic source records through permission checks, event matching, storage, and the event feed.</Copy><Copy muted>No live ticket listings, buy/wait advice, accounts, or notifications.</Copy></View>
        <Copy muted>Sweet Seats · Demo data only · Discovery first</Copy>
      </View>}
    />
  </KeyboardAvoidingView>;
}
const styles = StyleSheet.create({
  page: { paddingHorizontal: 22, maxWidth: 700, width: '100%', alignSelf: 'center' },
  header: { gap: 18, paddingBottom: 18 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  topbar: { paddingBottom: 20, borderBottomWidth: 1, marginBottom: 14 },
  brand: { fontFamily: fonts.serif, fontSize: 24, fontWeight: '700', letterSpacing: -0.8 },
  hero: { fontFamily: fonts.serif, fontSize: 43, lineHeight: 44, fontWeight: '700', letterSpacing: -2 },
  search: { flexDirection: 'row', alignItems: 'center', gap: 10, borderWidth: 1, borderRadius: 8, paddingHorizontal: 14 },
  input: { flex: 1, minHeight: 50, fontFamily: fonts.sans, fontSize: 14 },
  card: { padding: 20, borderWidth: 1, marginBottom: 16, overflow: 'hidden' },
  glow: { position: 'absolute', width: 210, height: 210, borderRadius: 105, top: -95, right: -95, opacity: 0.14 },
  date: { width: 54, paddingRight: 12, borderRightWidth: 1, alignItems: 'center', gap: 6 },
  day: { fontFamily: fonts.serif, fontSize: 36, lineHeight: 40, fontWeight: '700' },
  eventTitle: { fontFamily: fonts.serif, fontSize: 27, lineHeight: 29, fontWeight: '700', letterSpacing: -1 },
  about: { gap: 18, borderTopWidth: 1, paddingTop: 30 },
});
