import { useParams } from "react-router-dom";
import { ComingSoonPage } from "../components/ComingSoonPage";

export default function SharedPlanPage() {
  const { shareId } = useParams<{ shareId: string }>();
  return (
    <ComingSoonPage
      title="Shared plans arrive in the next update"
      message={
        shareId
          ? `Viewing shared plan ${shareId} will work once this page is wired up to GET /share/{id}.`
          : "Viewing a shared plan will work once this page is wired up to GET /share/{id}."
      }
    />
  );
}
