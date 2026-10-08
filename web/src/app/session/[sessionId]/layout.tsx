import { SessionAppShell } from "../../../components/ui";

export default async function SessionLayout(props: LayoutProps<"/session/[sessionId]">) {
  const { children, params } = props;
  const { sessionId } = await params;
  return <SessionAppShell sessionId={sessionId}>{children}</SessionAppShell>;
}
