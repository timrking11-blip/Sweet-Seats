import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useCallback } from 'react';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useGetDiscoveryEvent, getGetDiscoveryEventQueryKey } from '@workspace/api-client-react';
import { useColors } from '@/hooks/useColors';
import { Button, Copy, Eyebrow, Heading, Notice, RemoteState, eventTime, fonts, observedTime, usePageInsets } from '@/components/discovery-ui';

export default function EventDetailScreen() {
  const c = useColors();
  const insets = usePageInsets();
  const { id } = useLocalSearchParams<{ id: string }>();
  const eventId = typeof id === 'string' ? id : '';
  const detail = useGetDiscoveryEvent(encodeURIComponent(eventId), { query: { queryKey: getGetDiscoveryEventQueryKey(encodeURIComponent(eventId)), enabled: !!eventId }, request: { cache: 'no-store', timeoutMs: 8000 } });
  useFocusEffect(useCallback(() => { if (eventId) void detail.refetch(); }, [eventId, detail.refetch]));
  const status = detail.error?.status;
  const missing = !eventId || status === 404 || status === 422;
  const event = !detail.isError && !detail.isFetching && detail.data?.mode === 'synthetic' ? detail.data.event : undefined;
  return <ScrollView style={{ flex: 1, backgroundColor: c.background }} contentContainerStyle={[styles.page, insets]}>
    <View style={styles.nav}><Button label="← All events" testID="back-to-events" onPress={() => router.canGoBack() ? router.back() : router.replace('/')} /><Eyebrow>LOCAL DEMO</Eyebrow></View>
    {missing ? <RemoteState missing /> : detail.isFetching ? <RemoteState loading /> : !event ? <RemoteState retry={() => void detail.refetch()} /> : <>
      <Eyebrow>SYNTHETIC EVENT · {event.status.toUpperCase()}</Eyebrow>
      <Text accessibilityRole="header" style={[styles.title, { color: c.foreground }]}>{event.title}</Text>
      <Copy>{event.venue.name} · {event.venue.neighborhood}</Copy>
      <Copy>{event.local_date} · {eventTime(event)}</Copy>
      <Notice>{event.stale ? 'Stale observation. Recheck an official source before making plans.' : "Recent observation under the demo's 24-hour freshness rule."}</Notice>
      <Section><Heading>The lineup</Heading>
        {event.performers.length === 0 && <Copy muted>Lineup not provided.</Copy>}
        {event.performers.map(artist => <View key={`${artist.artist_id}:${artist.role}`} style={styles.lineup}><Text style={[styles.artist, { color: c.foreground }]}>{artist.name}</Text><Text style={{ color: c.primary }}>{artist.role}</Text></View>)}
      </Section>
      <Section><Heading>The source trail</Heading><Copy muted>Invented calendars and artists for local testing. These URLs are reserved placeholders, not live announcements.</Copy>
        {event.sources.length === 0 && <Copy muted>No source records provided.</Copy>}
        {event.sources.map(source => <View key={`${source.source_id}:${source.source_record_id}`} style={[styles.source, { backgroundColor: c.secondary, borderColor: c.border }]}>
          <Copy>{source.name}</Copy><Text selectable style={{ color: c.primary, fontFamily: fonts.sans, lineHeight: 21 }}>{source.source_url}</Text>
          <Copy muted>Source: {source.source_id}</Copy><Copy muted>Record: {source.source_record_id}</Copy>
          <Copy muted>Observed {observedTime(source.observed_at)}</Copy>
          <Copy muted>Available to Sweet Seats {observedTime(source.available_at)}</Copy>
        </View>)}
        <Copy muted>Event observed {observedTime(event.observed_at)}</Copy><Copy muted>Available {observedTime(event.available_at)}</Copy><Copy muted>Fresh until {observedTime(event.fresh_until)}</Copy>
      </Section>
      <Section><Heading>Tickets</Heading><Copy>{event.ticket_notice} Official ticket links arrive with a permitted live source.</Copy><Button label="No ticket link in this demo" disabled onPress={() => {}} /></Section>
      <Copy muted>Local demo · No live ticket listings or notifications</Copy>
    </>}
  </ScrollView>;
}
function Section({ children }: { children: React.ReactNode }) {
  const c = useColors();
  return <View style={[styles.section, { borderColor: c.border }]}>{children}</View>;
}
const styles = StyleSheet.create({
  page: { paddingHorizontal: 22, gap: 18, maxWidth: 700, width: '100%', alignSelf: 'center' },
  nav: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  title: { fontFamily: fonts.serif, fontSize: 44, lineHeight: 46, letterSpacing: -2, fontWeight: '700' },
  section: { borderTopWidth: 1, paddingTop: 28, marginTop: 8, gap: 18 },
  source: { padding: 18, borderWidth: 1, gap: 8 },
  lineup: { flexDirection: 'row', alignItems: 'center', gap: 18, justifyContent: 'space-between' },
  artist: { fontFamily: fonts.sans, fontWeight: '700', fontSize: 16, flex: 1 },
});
