import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import type { PropsWithChildren } from 'react';
import { Feather } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useColors } from '@/hooks/useColors';
import type { DiscoveryEvent, DiscoveryFeed } from '@workspace/api-client-react';

// Match the web's Georgia / Arial typography; Android uses its system serif / sans fallback.
export const fonts = {
  serif: Platform.select({ ios: 'Georgia', web: 'Georgia, "Times New Roman", serif', default: 'serif' }),
  sans: Platform.select({ ios: 'Arial', web: 'Arial, Helvetica, sans-serif', default: 'sans-serif' }),
};
export function usePageInsets() {
  const insets = useSafeAreaInsets();
  return { paddingTop: (Platform.OS === 'web' ? 67 : insets.top) + 16, paddingBottom: (Platform.OS === 'web' ? 34 : insets.bottom) + 24 };
}
export function Copy({ children, muted = false }: PropsWithChildren<{ muted?: boolean }>) {
  const c = useColors();
  return <Text style={[s.copy, { color: muted ? c.mutedForeground : c.foreground }]}>{children}</Text>;
}
export function Heading({ children }: PropsWithChildren) {
  const c = useColors();
  return <Text accessibilityRole="header" style={[s.heading, { color: c.foreground }]}>{children}</Text>;
}
export function Eyebrow({ children }: PropsWithChildren) {
  const c = useColors();
  return <Text style={[s.eyebrow, { color: c.primary }]}>{children}</Text>;
}
export function Button({ label, onPress, disabled = false, testID }: { label: string; onPress: () => void; disabled?: boolean; testID?: string }) {
  const c = useColors();
  return <Pressable testID={testID} accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress}
    style={({ pressed }) => [s.button, { borderColor: c.border, opacity: disabled ? 0.45 : pressed ? 0.65 : 1 }]}>
    <Text style={{ color: c.primary, fontFamily: fonts.sans, fontSize: 14, fontWeight: '700' }}>{label}</Text>
  </Pressable>;
}
export function Notice({ children }: PropsWithChildren) {
  const c = useColors();
  return <View style={[s.notice, { backgroundColor: c.muted, borderLeftColor: c.primary }]}><Copy>{children}</Copy></View>;
}
export function RemoteState({ loading = false, missing = false, retry }: { loading?: boolean; missing?: boolean; retry?: () => void }) {
  const c = useColors();
  return <View style={[s.state, { backgroundColor: c.secondary, borderColor: c.border }]} accessibilityLiveRegion="polite">
    {loading ? <><ActivityIndicator color={c.primary} /><Copy>Loading discovery…</Copy></> : <>
      <Feather name={missing ? 'eye-off' : 'cloud-off'} size={26} color={c.primary} />
      <Heading>{missing ? "This event isn't available." : 'Discovery is unavailable.'}</Heading>
      <Copy muted>{missing ? "It doesn't exist, or its sources don't currently permit display. This says nothing about ticket availability." : 'The local API or fixture store could not be read. We cannot infer event or ticket availability from this failure.'}</Copy>
      {retry && <Button label="Try again" onPress={retry} testID="retry" />}
    </>}
  </View>;
}
export function feedWarnings(data: DiscoveryFeed): string[] {
  const messages: string[] = [];
  if (data.status === 'partial') messages.push('A source failed. Previously observed events remain available; their timestamps have not been refreshed.');
  if (data.status === 'unavailable') messages.push('Source unavailable. This is a collection failure, not evidence of no events or sold-out tickets.');
  if (data.status === 'blocked') messages.push('Events are withheld because source permissions do not allow display or retention.');
  if (data.status === 'review_required' || data.review_count > 0) messages.push(`${data.review_count} source record(s) or event(s) withheld. Unresolved identities or conflicting facts need review; no match was guessed.`);
  return messages;
}
export function observedTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Timestamp unavailable';
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York', timeZoneName: 'short' }).format(date);
}
export function eventTime(event: DiscoveryEvent) {
  if (event.time_tba || !event.starts_at) return 'Time to be announced';
  try {
    return new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', timeZone: event.timezone, timeZoneName: 'short' }).format(new Date(event.starts_at));
  } catch { return 'Time unavailable'; }
}
export function matchesSearch(event: DiscoveryEvent, query: string) {
  return [event.title, event.venue.name, event.venue.neighborhood, ...event.performers.map(p => p.name)].join(' ').toLowerCase().includes(query.trim().toLowerCase());
}
export const s = StyleSheet.create({
  copy: { fontFamily: fonts.sans, fontSize: 14, lineHeight: 22 },
  heading: { fontFamily: fonts.serif, fontSize: 30, fontWeight: '700', letterSpacing: -1, lineHeight: 34 },
  eyebrow: { fontFamily: fonts.sans, fontSize: 10, fontWeight: '700', letterSpacing: 1.6 },
  button: { minHeight: 48, paddingHorizontal: 18, paddingVertical: 12, borderWidth: 1, borderRadius: 999, alignItems: 'center', justifyContent: 'center' },
  notice: { borderLeftWidth: 3, padding: 16, gap: 6 },
  state: { borderWidth: 1, padding: 24, gap: 18 },
});
