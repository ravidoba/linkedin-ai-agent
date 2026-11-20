
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  clearAccessToken,
  deleteResume,
  getAccessToken,
  getActiveResume,
  login,
  uploadResume,
  type ResumeSummary,
} from "../services/api";

export const MAX_RESUME_BYTES = 5 * 1024 * 1024;

function errorText(error: unknown): string {
  return error instanceof ApiError || error instanceof Error
    ? error.message
    : "Unknown error.";
}

function validate(file: File): string | undefined {
  const name = file.name.toLowerCase();

  if (!name.endsWith(".pdf") && !name.endsWith(".docx")) {
    return "Only PDF and DOCX files are supported.";
  }

  if (file.size === 0) {
    return "The selected file is empty.";
  }

  if (file.size > MAX_RESUME_BYTES) {
    return "Maximum file size is 5 MB.";
  }

  return undefined;
}

function fileKey(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

/**
 * Resume upload and permanent deletion state.
 * Resume contents are stored on the backend only.
 */
export function useResume() {
  const [signedIn, setSignedIn] = useState<boolean>(
    () => getAccessToken() !== null,
  );

  const [activeResume, setActiveResume] =
    useState<ResumeSummary | null>(null);

  const [selectedFile, setSelectedFile] =
    useState<File | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  const busyRef = useRef(false);
  const uploadedKeyRef = useRef<string | null>(null);

  const handleFailure = useCallback((err: unknown) => {
    if (err instanceof ApiError && err.kind === "cancelled") {
      return;
    }

    if (
      err instanceof ApiError &&
      err.status === 401 &&
      getAccessToken() === null
    ) {
      setSignedIn(false);
    }

    setError(errorText(err));
  }, []);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const resume = await getActiveResume(signal);

        if (!signal?.aborted) {
          setActiveResume(resume);
          setLoadFailed(false);
        }
      } catch (err) {
        if (!signal?.aborted) {
          setLoadFailed(true);
          handleFailure(err);
        }
      }
    },
    [handleFailure],
  );

  useEffect(() => {
    if (!signedIn) return;

    setActiveResume(null);

    const controller = new AbortController();
    void refresh(controller.signal);

    return () => controller.abort();
  }, [signedIn, refresh]);

  const signIn = async (email: string, password: string) => {
    if (busyRef.current) return;

    busyRef.current = true;
    setBusy(true);
    setError(null);

    try {
      await login(email, password);
      setSignedIn(true);
    } catch (err) {
      setError(errorText(err));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const signOut = () => {
    clearAccessToken();
    setSignedIn(false);
    setActiveResume(null);
    uploadedKeyRef.current = null;
    setSelectedFile(null);
    setError(null);
    setSuccess(null);
  };

  const selectFile = (file: File) => {
    setSuccess(null);

    const problem = validate(file);

    if (problem) {
      setSelectedFile(null);
      setError(problem);
      return;
    }

    if (fileKey(file) === uploadedKeyRef.current) {
      setSelectedFile(null);
      setError("This file was already uploaded.");
      return;
    }

    if (busyRef.current) return;

    setError(null);
    setSelectedFile(file);

    void upload(file);
  };

  const removeFile = () => {
    if (busyRef.current) return;

    setSelectedFile(null);
    setError(null);
  };

  const upload = async (file: File | null = selectedFile) => {
    if (!file || busyRef.current) return;

    busyRef.current = true;
    setBusy(true);
    setError(null);
    setSuccess(null);
    setLoadFailed(false);

    try {
      const saved = await uploadResume(file);

      setActiveResume(saved);
      uploadedKeyRef.current = fileKey(file);
      setSelectedFile(null);
      setSuccess(
        `Server confirmed active resume: ${saved.filename}`,
      );
    } catch (err) {
      handleFailure(err);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  /**
   * Permanently delete the active resume from the backend.
   * Preserve the UI state until the server confirms deletion.
   */
  const removeActiveResume = async () => {
    if (!activeResume || busyRef.current) return;

    busyRef.current = true;
    setBusy(true);
    setError(null);
    setSuccess(null);

    try {
      await deleteResume(activeResume.id);

      uploadedKeyRef.current = null;
      setSelectedFile(null);

      // Another previously uploaded resume may become active.
      await refresh();
    } catch (err) {
      handleFailure(err);

      // A network failure may have happened after server deletion.
      // Reconcile frontend state with the backend.
      await refresh();
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  return {
    signedIn,
    activeResume,
    selectedFile,
    busy,
    error,
    success,

    retryLoad: loadFailed
      ? () => {
          setError(null);
          void refresh();
        }
      : undefined,

    dismissError: () => setError(null),

    signIn,
    signOut,
    selectFile,
    removeFile,
    removeActiveResume,
    upload,
  };
}
